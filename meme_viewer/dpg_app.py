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
import platformdirs
from PIL import Image

from . import core

THUMB = (120, 90)
PREVIEW_MAX = (680, 600)
CELL_W = THUMB[0] + 16  # thumb + padding
CELL_H = THUMB[1] + 42  # thumb + label + spacing
CHROME_H = 150  # search + buttons + status + margins
COMPACT_W = 460
FULL_W = 1180
FULL_H = 780


def _config_path() -> Path:
    d = Path(platformdirs.user_config_dir("meme-viewer"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "window.json"


def load_config() -> dict:
    import json

    try:
        data = json.loads(_config_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(compact: bool) -> None:
    import json

    try:
        _config_path().write_text(json.dumps({"compact": compact}))
    except OSError:
        pass


def center_viewport() -> None:
    """Center the window using the real screen size. No-op if undetectable."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
    except Exception:
        return
    try:
        w, h = dpg.get_viewport_width(), dpg.get_viewport_height()
        dpg.set_viewport_pos([max(0, (sw - w) // 2), max(0, (sh - h) // 2)])
    except Exception:
        pass


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
        self.cols = 3
        self.compact = False
        self.full_w = FULL_W
        self.full_h = FULL_H

    def visible(self) -> list[str]:
        if not self.query:
            return self.names
        q = self.query.lower()
        return [n for n in self.names if q in n.lower()]

    def refresh(self) -> None:
        self.names = core.list_memes()
        if self.selected not in self.names:
            self.selected = self.names[0] if self.names else None
        self._fit_cols()
        build_grid(self)
        show_preview(self)
        if self.compact:
            fit_compact_height()

    def _fit_cols(self) -> bool:
        """Recompute column count from grid width. Returns True if changed."""
        try:
            w = dpg.get_item_rect_size("grid")[0]
        except Exception:
            return False
        cols = max(1, min(6, int(w // CELL_W))) if w > 0 else self.cols
        if cols != self.cols:
            self.cols = cols
            return True
        return False


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
        if i % g.cols == 0:
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
    if G.compact:
        fit_compact_height()


def on_viewport_resize() -> None:
    if G._fit_cols():
        build_grid(G)


def fit_compact_height() -> None:
    """Shrink the window to fit grid content — no dead gap at the bottom."""
    try:
        rows = max(1, -(-len(G.visible()) // max(1, G.cols)))
        dpg.set_viewport_height(max(280, min(900, CHROME_H + rows * CELL_H)))
    except Exception:
        pass


def set_compact(on: bool) -> None:
    G.compact = on
    save_config(on)
    if on:
        G.full_w = dpg.get_viewport_width()
        try:
            G.full_h = dpg.get_viewport_height()
        except Exception:
            pass
        dpg.hide_item("right_col")
        dpg.set_viewport_width(COMPACT_W)
        dpg.set_viewport_title("Meme Launcher")
    else:
        dpg.show_item("right_col")
        dpg.set_viewport_width(max(G.full_w, FULL_W - 200))
        dpg.set_viewport_height(G.full_h)
        dpg.set_viewport_title("Meme Viewer")
    G._fit_cols()
    build_grid(G)
    if on:
        fit_compact_height()
    center_viewport()


def toggle_compact() -> None:
    set_compact(not G.compact)


def copy_and_quit() -> None:
    items = G.visible()
    if G.selected not in items:
        G.selected = items[0] if items else None
    do_copy()
    dpg.stop_dearpygui()


def quit() -> None:
    for win in ("rename_win", "trash_win"):
        if dpg.is_item_shown(win):
            dpg.hide_item(win)
            return
    dpg.stop_dearpygui()


def search_focused() -> bool:
    try:
        return dpg.is_item_focused("search")
    except Exception:
        return False


def on_key_delete() -> None:
    if G.selected:
        dpg.show_item("trash_win")


def on_key_c() -> None:
    if dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_LSuper):
        do_copy()


def on_key_enter() -> None:
    if search_focused():
        items = G.visible()
        if items:
            G.selected = items[0]
            show_preview(G)
    copy_and_quit()


def on_key_escape() -> None:
    quit()


def on_key_e() -> None:
    if dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_LSuper):
        toggle_compact()


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
            dpg.add_button(label="Compact", callback=toggle_compact)
        with dpg.group(horizontal=True):
            with dpg.child_window(tag="grid", width=440, height=-30):
                pass
            with dpg.group(tag="right_col"):
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
        dpg.add_key_press_handler(dpg.mvKey_Return, callback=on_key_enter)
        dpg.add_key_press_handler(dpg.mvKey_Escape, callback=on_key_escape)
        dpg.add_key_press_handler(dpg.mvKey_E, callback=on_key_e)

    dpg.set_primary_window("main", True)


def main(argv: list[str] | None = None) -> None:
    import argparse

    p = argparse.ArgumentParser(description="Meme Viewer — native window.")
    p.add_argument("--compact", action="store_true", help="Launcher mode (narrow, no preview)")
    p.add_argument("--full", action="store_true", help="Force full mode (overrides saved compact)")
    p.add_argument("--width", type=int, default=FULL_W)
    p.add_argument("--height", type=int, default=780)
    args = p.parse_args(argv)

    saved_compact = bool(load_config().get("compact", False))
    want_compact = args.compact or (saved_compact and not args.full)

    dpg.create_context()
    dpg.create_viewport(title="Meme Viewer", width=args.width, height=args.height)
    apply_theme()
    build_ui()
    G.refresh()
    dpg.set_viewport_resize_callback(on_viewport_resize)
    if want_compact or args.width <= COMPACT_W + 40:
        set_compact(True)
    center_viewport()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    sys.exit(main())
