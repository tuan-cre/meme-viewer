"""Native desktop UI (Dear PyGui) — local-first, no browser, no Qt.

`meme-serve` (LAN share) and the browser UI in `static/` are untouched.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import dearpygui.dearpygui as dpg
from PIL import Image

from . import core

THUMB = (120, 90)
PREVIEW_MAX = (680, 600)
COLS = 3


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------
def _pil_rgba(path: Path, box: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    img.thumbnail(box)
    canvas = Image.new("RGBA", box, (0, 0, 0, 0))
    canvas.paste(img, ((box[0] - img.width) // 2, (box[1] - img.height) // 2), img)
    return canvas


def _tex_data(img: Image.Image) -> tuple[int, int, list[float]]:
    px = img.convert("RGBA")
    return px.width, px.height, [c / 255.0 for p in px.getdata() for c in p]


def copy_image_to_clipboard(path: Path) -> bool:
    """Best-effort image copy. Falls back to copying the file path as text."""
    system = platform.system()
    try:
        if system == "Windows":
            return _copy_windows(path)
        if system == "Linux":
            return _copy_linux(path)
    except Exception:
        pass
    dpg.set_clipboard_text(str(path))
    return False


def _copy_linux(path: Path) -> bool:
    data = path.read_bytes()
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        p = subprocess.run(
            ["wl-copy", "--type", "image/png"], input=data, capture_output=True
        )
        return p.returncode == 0
    if shutil.which("xclip"):
        p = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
            input=data,
            capture_output=True,
        )
        return p.returncode == 0
    return False


def _copy_windows(path: Path) -> bool:
    import ctypes

    img = Image.open(path).convert("RGB")
    buf = __import__("io").BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]  # strip BMP header -> DIB
    CF_DIB, GMEM_MOVEABLE = 8, 0x0002
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
    if not hmem:
        return False
    ptr = kernel32.GlobalLock(hmem)
    ctypes.memmove(ptr, dib, len(dib))
    kernel32.GlobalUnlock(hmem)
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(hmem)
        return False
    try:
        user32.EmptyClipboard()
        ok = bool(user32.SetClipboardData(CF_DIB, hmem))
    finally:
        user32.CloseClipboard()
    if not ok:
        kernel32.GlobalFree(hmem)
    return ok


def open_file(path: Path) -> None:
    if platform.system() == "Windows":
        os.startfile(path)  # noqa: S606
    else:
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, str(path)])


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class Gallery:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.selected: str | None = None
        self.query = ""

    def visible(self) -> list[str]:
        if not self.query:
            return self.names
        q = self.query.lower()
        return [n for n in self.names if q in n.lower()]

    def refresh(self) -> None:
        self.names = core.list_memes()
        if self.selected not in self.names:
            self.selected = self.names[0] if self.names else None
        build_grid(self)
        show_preview(self)


G = Gallery()


def status(msg: str) -> None:
    if dpg.does_item_exist("status"):
        dpg.set_value("status", msg)


def build_grid(g: Gallery) -> None:
    dpg.delete_item("grid", children_only=True)
    items = g.visible()
    if not items:
        dpg.add_text("No memes — press Add.", parent="grid")
        return
    row = None
    for i, name in enumerate(items):
        if i % COLS == 0:
            row = dpg.add_group(horizontal=True, parent="grid")
        cell = dpg.add_group(horizontal=False, parent=row)
        path = core.resolve(name)
        try:
            w, h, data = _tex_data(_pil_rgba(path, THUMB))
            tex = dpg.add_static_texture(w, h, data, parent="texreg")
            dpg.add_image_button(
                tex, width=THUMB[0], height=THUMB[1], parent=cell,
                callback=lambda s, a, u=name: select(u),
            )
        except Exception:
            dpg.add_text("[bad image]", parent=cell)
        label = name if len(name) <= 20 else name[:19] + "…"
        dpg.add_text(label, parent=cell)


def show_preview(g: Gallery) -> None:
    dpg.delete_item("preview_img", children_only=True)
    dpg.delete_item("preview_bar", children_only=True)
    if not g.selected:
        dpg.add_text("Select a meme", parent="preview_img")
        return
    path = core.resolve(g.selected)
    if path is None:
        return
    try:
        w, h, data = _tex_data(_pil_rgba(path, PREVIEW_MAX))
        tex = dpg.add_static_texture(w, h, data, parent="texreg")
        dpg.add_image(tex, width=w, height=h, parent="preview_img")
    except Exception:
        dpg.add_text("Failed to load image", parent="preview_img")
        return
    with dpg.group(horizontal=True, parent="preview_bar"):
        dpg.add_text(g.selected)
        dpg.add_button(label="Copy", callback=lambda: do_copy())
        dpg.add_button(label="Open", callback=lambda: open_file(path))
        dpg.add_button(label="Rename", callback=lambda: dpg.show_item("rename_win"))
        dpg.add_button(label="Trash", callback=lambda: dpg.show_item("trash_win"))


def select(name: str) -> None:
    G.selected = name
    show_preview(G)


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
def do_copy() -> None:
    if not G.selected:
        return
    path = core.resolve(G.selected)
    if path is None:
        return
    if copy_image_to_clipboard(path):
        status(f"Copied {G.selected}")
    else:
        status(f"Clipboard tool missing — path copied: {G.selected}")


def do_trash() -> None:
    if G.selected and core.trash(G.selected):
        status(f"Trashed {G.selected}")
        G.selected = None
        G.refresh()
    dpg.hide_item("trash_win")


def do_rename() -> None:
    if not G.selected:
        return
    new = dpg.get_value("rename_input").strip()
    if not new:
        return
    result = core.rename(G.selected, new)
    dpg.hide_item("rename_win")
    if result is None:
        status("Rename failed (bad name or exists)")
        return
    status(f"Renamed to {result}")
    G.selected = result
    G.refresh()


def on_add_dialog(_s, app_data) -> None:
    paths = [Path(p) for p in app_data.get("selections", {}).values()]
    n = core.add_files(paths)
    status(f"Added {n} file(s)" if n else "Nothing added")
    G.refresh()


def on_search(_s, text: str) -> None:
    G.query = text
    build_grid(G)


def on_key_delete() -> None:
    if G.selected:
        dpg.show_item("trash_win")


def on_key_c() -> None:
    if dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_LSuper):
        do_copy()


# --------------------------------------------------------------------------
# Theme + layout
# --------------------------------------------------------------------------
def apply_theme() -> None:
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (5, 5, 8))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (8, 8, 13))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (15, 15, 24))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (26, 20, 35))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (40, 30, 52))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (199, 160, 200))
    dpg.bind_theme(t)


def build_ui() -> None:
    dpg.add_texture_registry(tag="texreg")

    with dpg.window(tag="main", label="Meme Viewer"):
        dpg.add_input_text(
            tag="search", hint="Search memes...", callback=on_search, width=-1
        )
        with dpg.group(horizontal=True):
            dpg.add_button(label="+ Add", callback=lambda: dpg.show_item("add_dialog"))
            dpg.add_button(label="Refresh", callback=lambda: G.refresh())
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="grid", width=440, height=-30):
                pass
            with dpg.group():
                with dpg.child_window(tag="preview_img", width=-1, height=-60):
                    pass
                with dpg.group(tag="preview_bar"):
                    pass
        dpg.add_text("", tag="status")

    with dpg.file_dialog(
        tag="add_dialog", show=False, modal=True, width=600, height=400,
        callback=on_add_dialog,
    ):
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            dpg.add_file_extension(ext)

    with dpg.window(
        tag="rename_win", label="Rename", modal=True, show=False,
        width=360, height=120,
    ):
        dpg.add_input_text(tag="rename_input", width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="OK", callback=do_rename)
            dpg.add_button(
                label="Cancel", callback=lambda: dpg.hide_item("rename_win")
            )

    with dpg.window(
        tag="trash_win", label="Trash", modal=True, show=False,
        width=300, height=110,
    ):
        dpg.add_text("Move to trash?")
        with dpg.group(horizontal=True):
            dpg.add_button(label="Yes", callback=do_trash)
            dpg.add_button(
                label="No", callback=lambda: dpg.hide_item("trash_win")
            )

    with dpg.handler_registry():
        dpg.add_key_press_handler(dpg.mvKey_Delete, callback=on_key_delete)
        dpg.add_key_press_handler(dpg.mvKey_C, callback=on_key_c)

    dpg.set_primary_window("main", True)


def main() -> None:
    dpg.create_context()
    dpg.create_viewport(title="Meme Viewer", width=1180, height=780)
    apply_theme()
    build_ui()
    G.refresh()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    sys.exit(main())
