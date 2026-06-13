from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QPixmap, QKeySequence, QPainter, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

MEMES_DIR = Path.home() / ".local" / "share" / "memes"
TRASH_DIR = MEMES_DIR / ".trash"
THUMB_W = 120
THUMB_H = 90
PREVIEW_W = 520


STYLE_SHEET = """
* {
    background-color: #050508;
    color: #c7a0c8;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background-color: #050508;
}

QListWidget {
    background-color: #08080d;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget::item {
    padding: 2px;
    margin: 1px 0;
    border-radius: 6px;
    color: #c7a0c8;
}
QListWidget::item:hover {
    background-color: #0f0f18;
}
QListWidget::item:selected {
    background-color: #1a1423;
    border: 1px solid #b48ead;
}

QScrollArea {
    background-color: #050508;
    border: none;
}
QScrollBar:vertical {
    background: #08080d;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #1a1423;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #08080d;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #1a1423;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QToolBar {
    background-color: #08080d;
    border-bottom: 1px solid #1a1423;
    spacing: 4px;
    padding: 2px;
}
QToolBar QToolButton {
    color: #c7a0c8;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
}
QToolBar QToolButton:hover {
    background-color: #0f0f18;
    border-color: #b48ead;
}
QToolBar QToolButton:pressed {
    background-color: #1a1423;
}

QLabel#placeholder {
    color: #5c5c6e;
    font-size: 18px;
    qproperty-alignment: AlignCenter;
}

QInputDialog, QMessageBox {
    background-color: #08080d;
}
"""


def _trash_dir() -> Path:
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    return TRASH_DIR


def _load_thumb(path: Path) -> QIcon:
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return QIcon()
    scaled = pixmap.scaled(
        THUMB_W,
        THUMB_H,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(THUMB_W, THUMB_H)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawPixmap(
        (THUMB_W - scaled.width()) // 2,
        (THUMB_H - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return QIcon(canvas)


class MemeList(QListWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSpacing(1)


class PreviewPanel(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Select a meme")
        self._label.setObjectName("placeholder")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self._label)
        self.setWidgetResizable(True)

    def show_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._label.setText("Failed to load image")
            return
        self._label.setObjectName("")
        # Scale image to fit the scroll area's viewport, centered
        if self.width() > 0 and self.height() > 0:
            scaled = pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
            )
            self._label.setPixmap(scaled)
        else:
            self._label.setPixmap(pixmap)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def clear_preview(self) -> None:
        self._label.setObjectName("placeholder")
        self._label.setPixmap(QPixmap())
        self._label.setText("Select a meme")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Meme Collection QL")
        self.resize(400, 800)
        self._clipboard_modified = False
        self._preview_visible = False
        self._base_width = 400
        self._saved_width = 400

        self.list_widget = MemeList()
        self.preview = PreviewPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # Start collapsed — right panel width = 0
        splitter.setSizes([self._base_width, 0])
        self.preview.setMinimumWidth(0)
        self.preview.setMaximumWidth(0)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self._splitter = splitter

        self.list_widget.currentItemChanged.connect(self._on_select)
        self.list_widget.itemActivated.connect(self._copy_and_exit)

        self._build_toolbar()
        self._build_context_menu()
        self._scan_dir()

        # Restore collapsed state after _scan_dir (which selects row 0)
        self._apply_collapsed()
        print(f"[debug] init: after _apply_collapsed width={self.width()} _saved_width={self._saved_width}")

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._copy_meme)
        toolbar.addAction(copy_action)

        trash_action = QAction("Trash", self)
        trash_action.setShortcuts([QKeySequence("Ctrl+D"), QKeySequence.StandardKey.Delete])
        trash_action.triggered.connect(self._trash_meme)
        toolbar.addAction(trash_action)

        rename_action = QAction("Rename", self)
        rename_action.setShortcut(QKeySequence("Ctrl+R"))
        rename_action.triggered.connect(self._rename_meme)
        toolbar.addAction(rename_action)

        preview_action = QAction("Preview", self)
        preview_action.setShortcuts([QKeySequence("Ctrl+E"), QKeySequence("Space")])
        preview_action.triggered.connect(self._toggle_preview)
        toolbar.addAction(preview_action)

        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.triggered.connect(self._scan_dir)
        toolbar.addAction(refresh_action)

    def _build_context_menu(self) -> None:
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        copy_act = menu.addAction("Copy")
        trash_act = menu.addAction("Trash")
        rename_act = menu.addAction("Rename")
        preview_act = menu.addAction("Preview")
        view_act = menu.addAction("Full View")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == copy_act:
            self._copy_meme()
        elif action == trash_act:
            self._trash_meme()
        elif action == rename_act:
            self._rename_meme()
        elif action == preview_act:
            self._toggle_preview()
        elif action == view_act:
            self._open_full()

    # ------------------------------------------------------------------
    # Preview panel logic
    # ------------------------------------------------------------------
    def _on_select(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current is None:
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        self.preview.show_pixmap(path)

    def _apply_collapsed(self) -> None:
        self.preview.setMinimumWidth(0)
        new_w = max(self._saved_width, self._base_width)
        print(f"[debug] collapse: _saved_width={self._saved_width} _base_width={self._base_width} new_w={new_w}")
        self._splitter.setSizes([new_w, 0])
        self.preview.setMaximumWidth(0)
        self.resize(new_w, self.height())
        print(f"[debug] collapse: after resize width={self.width()}")
        self._preview_visible = False

    def _apply_expanded(self) -> None:
        # Save current window width so collapse can restore it exactly
        self._saved_width = self.width()
        print(f"[debug] expand: saved_width set to {self._saved_width}")
        # Grow the window width to make room — left panel stays fixed
        sizes = self._splitter.sizes()
        left_width = sizes[0] if sizes else self._base_width
        new_w = self.width() + PREVIEW_W
        print(f"[debug] expand: left_width={left_width} self.width()={self.width()} new_w={new_w}")
        self.resize(new_w, self.height())
        self._splitter.setSizes([left_width, PREVIEW_W])
        self.preview.setMinimumWidth(PREVIEW_W)
        self.preview.setMaximumWidth(16777215)
        self._preview_visible = True
        # Refresh the displayed image to scale to new viewport size
        current_item = self.list_widget.currentItem()
        if current_item:
            self._on_select(current_item, None)

    def _toggle_preview(self) -> None:
        if self._preview_visible:
            self._apply_collapsed()
        else:
            self._apply_expanded()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _scan_dir(self) -> None:
        if not MEMES_DIR.exists():
            MEMES_DIR.mkdir(parents=True, exist_ok=True)
        exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        files = sorted(
            p for p in MEMES_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts
        )
        self.list_widget.clear()
        for path in files:
            item = QListWidgetItem(_load_thumb(path), path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview.clear_preview()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _selected_path(self) -> Path | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _copy_and_exit(self) -> None:
        path = self._selected_path()
        if path is not None and path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                clipboard = QApplication.clipboard()
                clipboard.setImage(pixmap.toImage())
                self._clipboard_modified = True
                self._copied_pixmap = pixmap
        QTimer.singleShot(0, QApplication.quit)

    def _copy_meme(self) -> None:
        path = self._selected_path()
        if path is None or not path.exists():
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        self._clipboard_modified = True
        self._copied_pixmap = pixmap

    def _trash_meme(self) -> None:
        path = self._selected_path()
        if path is None or not path.exists():
            return
        reply = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move {path.name} to trash?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        dest = _trash_dir() / path.name
        counter = 1
        base = dest.stem
        while dest.exists():
            dest = _trash_dir() / f"{base}_{counter}{path.suffix}"
            counter += 1
        shutil.move(str(path), str(dest))
        self._clipboard_modified = True
        self._scan_dir()

    def _rename_meme(self) -> None:
        path = self._selected_path()
        if path is None or not path.exists():
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Meme",
            "New filename:",
            text=path.name,
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        if new_name == path.name:
            return
        new_path = path.with_name(new_name)
        if new_path.exists() and new_path != path:
            QMessageBox.warning(self, "Rename Failed", "A file with that name already exists.")
            return
        path.rename(new_path)
        self._scan_dir()

    def _open_full(self) -> None:
        path = self._selected_path()
        if path is None or not path.exists():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._clipboard_modified = False
        event.accept()


def main() -> None:
    import sys

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    screen = app.primaryScreen().availableGeometry()
    geo = window.geometry()
    geo.moveCenter(screen.center())
    window.setGeometry(geo)
    print(f"[debug] main: after setGeometry width={window.width()} frame={window.geometry().width()}")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
