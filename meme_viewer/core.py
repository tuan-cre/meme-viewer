"""Core storage logic — no UI, no HTTP. Shared by server and CLI."""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import platformdirs
from PIL import Image

EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
THUMB_W = 120
THUMB_H = 90


def memes_dir() -> Path:
    d = Path(platformdirs.user_data_dir("memes"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def trash_dir() -> Path:
    d = memes_dir() / ".trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _recent_file() -> Path:
    return memes_dir() / ".recent.json"


def load_recents() -> dict[str, float]:
    try:
        data = json.loads(_recent_file().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_used(name: str) -> None:
    """Record a use (copy/open) so future listings sort it first."""
    try:
        recents = load_recents()
        recents[name] = time.time()
        _recent_file().write_text(json.dumps(recents))
    except OSError:
        pass


def list_memes() -> list[str]:
    d = memes_dir()
    if not d.exists():
        return []
    names = sorted(
        p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXTS
    )
    # Most recently used first; never-used keep alphabetical order at the end
    recents = load_recents()
    names.sort(key=lambda n: recents.get(n, 0), reverse=True)
    return names


def resolve(name: str) -> Path | None:
    """Return MEMES_DIR / name if safe, else None. Blocks traversal."""
    if not name or "/" in name or "\\" in name:
        return None
    if Path(name).name != name or name in {".", ".."}:
        return None
    p = memes_dir() / name
    try:
        p.resolve().relative_to(memes_dir().resolve())
    except (ValueError, OSError):
        return None
    return p


def unique_dest(name: str) -> Path:
    dest = memes_dir() / name
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while dest.exists():
        dest = memes_dir() / f"{stem}_{i}{suffix}"
        i += 1
    return dest


def add_files(paths: list[Path]) -> int:
    """Copy image files into the collection. Returns count added."""
    import shutil

    count = 0
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in EXTS:
            continue
        try:
            shutil.copy2(path, unique_dest(path.name))
            count += 1
        except OSError:
            pass
    return count


def add_bytes(data: bytes, filename: str) -> str | None:
    """Save raw image bytes into the collection. Returns filename or None."""
    if not data:
        return None
    clean = Path(filename).name
    if not clean or not any(clean.lower().endswith(e) for e in EXTS):
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception:
        return None
    try:
        dest = unique_dest(clean)
        dest.write_bytes(data)
        return dest.name
    except OSError:
        return None


def trash(name: str) -> bool:
    src = resolve(name)
    if src is None or not src.is_file():
        return False
    dest = trash_dir() / src.name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        i = 1
        while dest.exists():
            dest = trash_dir() / f"{stem}_{i}{suffix}"
            i += 1
    src.rename(dest)
    return True


def rename(old: str, new: str) -> str | None:
    """Rename meme. Returns new filename or None on failure. Mirrors Qt logic."""
    src = resolve(old)
    if src is None or not src.is_file():
        return None
    new = new.strip()
    if not new or new == src.name:
        return None
    if not any(new.lower().endswith(e) for e in EXTS):
        new += src.suffix
    if "/" in new or "\\" in new or Path(new).name != new:
        return None
    dest = memes_dir() / new
    if dest.exists() and dest != src:
        return None
    try:
        src.rename(dest)
    except OSError:
        return None
    return dest.name


def make_thumb(path: Path) -> bytes:
    """120x90 transparent PNG, image centered. Raises on failure."""
    img = Image.open(path)
    img.thumbnail((THUMB_W, THUMB_H))
    canvas = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    x = (THUMB_W - img.width) // 2
    y = (THUMB_H - img.height) // 2
    if img.mode in ("RGBA", "LA"):
        canvas.paste(img, (x, y), img)
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        canvas.paste(img, (x, y))
    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()
