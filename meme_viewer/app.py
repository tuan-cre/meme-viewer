from __future__ import annotations

import json
import shutil
import time
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QIcon, QPixmap, QKeySequence, QPainter, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

MEMES_DIR = Path.home() / ".local" / "share" / "memes"
TRASH_DIR = MEMES_DIR / ".trash"
RECENT_FILE = MEMES_DIR / ".recent.json"
THUMB_W = 120
THUMB_H = 90
PREVIEW_W = 520

SERVER_URL_FILE = Path.home() / ".config" / "meme-viewer" / "server_url"


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

QLineEdit#search_bar {
    background-color: #0f0f18;
    border: 1px solid #1a1423;
    border-radius: 6px;
    padding: 6px 10px;
    color: #c7a0c8;
    selection-background-color: #b48ead;
    selection-color: #050508;
    font-size: 13px;
}
QLineEdit#search_bar:focus {
    border-color: #b48ead;
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
        self.set_pixmap(pixmap)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Display a QPixmap directly (used for remote downloads)."""
        self._label.setObjectName("")
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
        self._recents: dict[str, float] = self._load_recents()
        self._remote_url: str = self._load_server_url()

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
        self._build_searchbar()
        layout.addWidget(self.search_bar)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self._splitter = splitter

        # Tab toggles between search bar and list (not individual items)
        self.list_widget.setTabKeyNavigation(False)
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.list_widget.currentItemChanged.connect(self._on_select)
        self.list_widget.itemActivated.connect(self._copy_and_exit)

        self._build_shortcuts()
        self._build_context_menu()

        if self._remote_url:
            # Auto-connect to saved remote server after event loop starts
            QTimer.singleShot(0, lambda: self._connect_remote(self._remote_url))
        else:
            self._scan_dir()

        # Restore collapsed state after _scan_dir (which selects row 0)
        if not self._remote_url:
            self._apply_collapsed()
        print(f"[debug] init: after _apply_collapsed width={self.width()} _saved_width={self._saved_width}")

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_searchbar(self) -> None:
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("search_bar")
        self.search_bar.setPlaceholderText("Search memes...")
        self.search_bar.textChanged.connect(self._filter_list)

    def _filter_list(self, text: str) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            item.setHidden(text.lower() not in item.text().lower())

    def _build_shortcuts(self) -> None:
        act = QAction("Copy", self)
        act.setShortcuts([QKeySequence("Ctrl+C"), QKeySequence.StandardKey.Copy])
        act.triggered.connect(self._copy_meme)
        self.addAction(act)

        act = QAction("Trash", self)
        act.setShortcuts([QKeySequence("Ctrl+D"), QKeySequence.StandardKey.Delete])
        act.triggered.connect(self._trash_meme)
        self.addAction(act)

        act = QAction("Rename", self)
        act.setShortcut(QKeySequence("Ctrl+R"))
        act.triggered.connect(self._rename_meme)
        self.addAction(act)

        act = QAction("Preview", self)
        act.setShortcuts([QKeySequence("Ctrl+E"), QKeySequence("Space")])
        act.triggered.connect(self._toggle_preview)
        self.addAction(act)

        act = QAction("Refresh", self)
        act.setShortcut(QKeySequence.StandardKey.Refresh)
        act.triggered.connect(self._refresh)
        self.addAction(act)

        act = QAction("Server Mode", self)
        act.setShortcut(QKeySequence("Ctrl+S"))
        act.triggered.connect(self._toggle_mode)
        self.addAction(act)

        del act

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
        menu.addSeparator()
        preview_act = menu.addAction("Preview")
        view_act = menu.addAction("Full View")
        trash_act = rename_act = None
        if not self._remote_url:
            menu.addSeparator()
            trash_act = menu.addAction("Trash")
            rename_act = menu.addAction("Rename")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == copy_act:
            self._copy_meme()
        elif action == preview_act:
            self._toggle_preview()
        elif action == view_act:
            self._open_full()
        elif action is not None and action == trash_act:
            self._trash_meme()
        elif action is not None and action == rename_act:
            self._rename_meme()

    # ------------------------------------------------------------------
    # Preview panel logic
    # ------------------------------------------------------------------
    def _on_select(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        if self._remote_url:
            pixmap = self._download_image(self._remote_image_url(name))
            if pixmap is not None:
                self.preview.set_pixmap(pixmap)
            else:
                self.preview.clear_preview()
        else:
            self.preview.show_pixmap(Path(name))

    def _apply_collapsed(self) -> None:
        new_w = max(self._saved_width, self._base_width)
        print(f"[debug] collapse: _saved_width={self._saved_width} _base_width={self._base_width} new_w={new_w}")
        # Disable preview constraints BEFORE splitter sizing
        self.preview.setMinimumWidth(0)
        self.preview.setMaximumWidth(0)
        self._splitter.setSizes([new_w, 0])
        self._preview_visible = False
        # Force window to desired width (splitter's size request can fight resize)
        self.resize(new_w, self.height())
        print(f"[debug] collapse: after resize width={self.width()}")
        if self.width() != new_w:
            print(f"[debug] collapse: width mismatch, forcing to {new_w}")
            self.setFixedWidth(new_w)
            QTimer.singleShot(0, lambda: (
                self.setMinimumWidth(0),
                self.setMaximumWidth(16777215),
            ))

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
    # Remote / Server client mode
    # ------------------------------------------------------------------
    def _load_server_url(self) -> str:
        try:
            if SERVER_URL_FILE.exists():
                data = SERVER_URL_FILE.read_text().strip()
                if data.startswith("http://") or data.startswith("https://"):
                    return data
        except OSError:
            pass
        return ""

    def _save_server_url(self, url: str) -> None:
        try:
            SERVER_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
            SERVER_URL_FILE.write_text(url)
        except OSError:
            pass

    def _toggle_mode(self) -> None:
        if self._remote_url:
            self._disconnect_remote()
        else:
            url, ok = QInputDialog.getText(
                self,
                "Connect to Server",
                "Enter meme-serve URL (e.g. http://192.168.1.68:8765):",
                text=self._load_server_url(),
            )
            if not ok or not url or not url.strip():
                return
            url = url.strip().rstrip("/")
            self._connect_remote(url)

    def _connect_remote(self, url: str) -> None:
        """Fetch remote meme list and switch to remote mode."""
        try:
            resp = urllib.request.urlopen(f"{url}/api/memes", timeout=5)
            names: list[str] = json.loads(resp.read().decode())
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", f"Could not fetch memes:\n{e}")
            return

        self._remote_url = url
        self._save_server_url(url)
        self.list_widget.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview.clear_preview()

        self.setWindowTitle(f"Meme Collection QL  [ {url} ]")
        print(f"[remote] connected to {url} ({len(names)} memes)")

        # Fetch thumbnails in background
        QTimer.singleShot(0, lambda: self._fetch_remote_thumbs(url))

    def _fetch_remote_thumbs(self, url: str) -> None:
        icons: dict[str, QIcon] = {}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            name = item.data(Qt.ItemDataRole.UserRole) or item.text()
            try:
                resp = urllib.request.urlopen(f"{url}/thumb/{name}", timeout=5)
                pixmap = QPixmap()
                if pixmap.loadFromData(resp.read()) and not pixmap.isNull():
                    icons[name] = QIcon(pixmap)
            except Exception:
                pass
            QApplication.processEvents()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            name = item.data(Qt.ItemDataRole.UserRole) or item.text()
            icon = icons.get(name)
            if icon is not None:
                item.setIcon(icon)

    def _disconnect_remote(self) -> None:
        """Switch back to local mode."""
        self._remote_url = ""
        self.setWindowTitle("Meme Collection QL")
        self._scan_dir()
        print("[remote] disconnected")

    def _remote_image_url(self, name: str) -> str:
        return f"{self._remote_url}/images/{name}"

    def _download_image(self, url: str) -> QPixmap | None:
        """Download an image from URL and return as QPixmap."""
        try:
            data = urllib.request.urlopen(url, timeout=10).read()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                return pixmap
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Recency tracking
    # ------------------------------------------------------------------
    @staticmethod
    def _load_recents() -> dict[str, float]:
        if RECENT_FILE.exists():
            try:
                data = json.loads(RECENT_FILE.read_text())
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_recents(self) -> None:
        try:
            RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
            RECENT_FILE.write_text(json.dumps(self._recents, indent=0))
        except OSError:
            pass

    def _mark_used(self, path: Path) -> None:
        self._recents[path.name] = time.time()
        self._save_recents()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _scan_dir(self) -> None:
        if not MEMES_DIR.exists():
            MEMES_DIR.mkdir(parents=True, exist_ok=True)
        exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        files = [
            p for p in MEMES_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts
        ]
        # Sort by recency — most recently used first, untracked files at end
        files.sort(key=lambda p: self._recents.get(p.name, 0), reverse=True)
        self.list_widget.clear()
        for path in files:
            item = QListWidgetItem(_load_thumb(path), path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self.preview.clear_preview()

    def _refresh(self) -> None:
        if self._remote_url:
            self._connect_remote(self._remote_url)
        else:
            self._scan_dir()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _selected_path(self) -> Path | None:
        if self._remote_url:
            return None
        name = self._selected_name()
        return Path(name) if name else None

    def _copy_and_exit(self) -> None:
        name = self._selected_name()
        if name is None:
            QTimer.singleShot(0, QApplication.quit)
            return
        if self._remote_url:
            pixmap = self._download_image(self._remote_image_url(name))
        else:
            path = Path(name)
            pixmap = QPixmap(str(path)) if path.exists() else None
        if pixmap is not None and not pixmap.isNull():
            clipboard = QApplication.clipboard()
            clipboard.setImage(pixmap.toImage())
            self._clipboard_modified = True
            self._copied_pixmap = pixmap
            if not self._remote_url:
                self._mark_used(Path(name))
        QTimer.singleShot(0, QApplication.quit)

    def _copy_meme(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        if self._remote_url:
            pixmap = self._download_image(self._remote_image_url(name))
        else:
            path = Path(name)
            if not path.exists():
                return
            pixmap = QPixmap(str(path))
        if pixmap is None or pixmap.isNull():
            return
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        self._clipboard_modified = True
        self._copied_pixmap = pixmap
        if not self._remote_url:
            self._mark_used(Path(name))

    def _trash_meme(self) -> None:
        if self._remote_url:
            return
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
        if self._remote_url:
            return
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
        name = self._selected_name()
        if name is None:
            return
        if self._remote_url:
            QDesktopServices.openUrl(QUrl(self._remote_image_url(name)))
        else:
            path = Path(name)
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                self._mark_used(path)

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
