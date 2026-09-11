"""Core storage tests — run against an isolated tmp dir."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from meme_viewer import core


@pytest.fixture
def memes(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "memes_dir", lambda: tmp_path)
    return tmp_path


def _png(path, color=(255, 0, 0), size=(200, 100)):
    img = Image.new("RGB", size, color)
    img.save(path, "PNG")


def test_resolve_blocks_traversal(memes):
    assert core.resolve("../secret") is None
    assert core.resolve("a/b.png") is None
    assert core.resolve("..\\x.png") is None
    assert core.resolve("") is None
    assert core.resolve(".") is None
    (memes / "ok.png").write_bytes(b"x")
    assert core.resolve("ok.png") == memes / "ok.png"


def test_unique_dest(memes):
    (memes / "a.png").write_bytes(b"x")
    assert core.unique_dest("a.png") == memes / "a_1.png"
    assert core.unique_dest("b.png") == memes / "b.png"


def test_trash_moves_file(memes):
    (memes / "m.png").write_bytes(b"x")
    assert core.trash("m.png") is True
    assert not (memes / "m.png").exists()
    assert (memes / ".trash" / "m.png").exists()
    assert core.trash("missing.png") is False
    assert core.trash("../evil") is False


def test_rename_auto_ext_and_guards(memes):
    (memes / "old.png").write_bytes(b"x")
    assert core.rename("old.png", "new") == "new.png"  # auto-adds suffix
    assert core.rename("new.png", "../evil.png") is None
    (memes / "taken.png").write_bytes(b"x")
    assert core.rename("new.png", "taken.png") is None  # exists
    assert core.rename("missing.png", "x.png") is None


def test_make_thumb_is_png_canvas(memes):
    _png(memes / "big.png", size=(400, 300))
    data = core.make_thumb(memes / "big.png")
    img = Image.open(io.BytesIO(data))
    assert img.size == (core.THUMB_W, core.THUMB_H)


def test_list_memes_sorted_and_filtered(memes):
    _png(memes / "b.png")
    _png(memes / "a.jpg")
    (memes / "note.txt").write_text("nope")
    assert core.list_memes() == ["a.jpg", "b.png"]


def test_add_files_copies_and_dedupes(memes, tmp_path):
    from pathlib import Path

    src = tmp_path / "src"
    src.mkdir()
    (src / "x.png").write_bytes(b"img")
    (src / "skip.txt").write_text("nope")
    assert core.add_files([src / "x.png", src / "skip.txt"]) == 1
    assert (memes / "x.png").exists()
    assert core.add_files([src / "x.png"]) == 1  # dedupes to x_1.png
    assert (memes / "x_1.png").exists()
    assert core.add_files([Path("/nonexistent.png")]) == 0


def test_recent_use_sorts_first(memes):
    for n in ("a.png", "b.png", "c.png"):
        (memes / n).write_bytes(b"x")
    assert core.list_memes() == ["a.png", "b.png", "c.png"]
    core.mark_used("c.png")
    assert core.list_memes()[0] == "c.png"
    core.mark_used("b.png")
    assert core.list_memes()[:2] == ["b.png", "c.png"]
