"""FastAPI server — the only backend. Serves JSON API + static web UI."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import core

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="meme-viewer")


class RenameReq(BaseModel):
    old: str
    new: str


class TrashReq(BaseModel):
    name: str


def _check(name: str) -> Path:
    p = core.resolve(name)
    if p is None or not p.is_file():
        raise HTTPException(404, "Not found")
    return p


@app.get("/api/memes", response_model=list[str])
def api_memes(q: str = "") -> list[str]:
    names = core.list_memes()
    if q:
        ql = q.lower()
        names = [n for n in names if ql in n.lower()]
    return names


@app.get("/images/{name}")
def get_image(name: str):
    p = _check(name)
    ctype, _ = mimetypes.guess_type(p.name)
    return FileResponse(
        p,
        media_type=ctype or "application/octet-stream",
        headers={"Cache-Control": "max-age=3600"},
    )


@app.get("/thumb/{name}")
def get_thumb(name: str):
    p = _check(name)
    try:
        data = core.make_thumb(p)
    except Exception:
        raise HTTPException(404, "Bad image")
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "max-age=3600"},
    )


def _save_bytes(filename: str, data: bytes) -> str:
    if not data:
        raise HTTPException(400, "Empty data")
    clean = Path(filename).name
    if not clean or not any(clean.lower().endswith(e) for e in core.EXTS):
        raise HTTPException(400, "Not an image filename")
    dest = core.unique_dest(clean)
    dest.write_bytes(data)
    return dest.name


@app.post("/upload", response_model=list[str])
async def upload(files: list[UploadFile] = File(...)) -> list[str]:
    saved = []
    for f in files:
        data = await f.read()
        saved.append(_save_bytes(f.filename or "upload", data))
    return saved


@app.post("/upload/{name}")
async def upload_raw(name: str, request: Request):
    """Legacy compat: raw octet-stream body (old Qt client)."""
    from urllib.parse import unquote

    data = await request.body()
    saved = _save_bytes(unquote(name), data)
    return {"ok": True, "filename": saved}


@app.post("/api/rename")
def api_rename(req: RenameReq):
    result = core.rename(req.old, req.new)
    if result is None:
        raise HTTPException(400, "Rename failed (bad name or exists)")
    return {"ok": True, "filename": result}


@app.post("/api/trash")
def api_trash(req: TrashReq):
    if not core.trash(req.name):
        raise HTTPException(404, "Not found")
    return {"ok": True}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    html = STATIC_DIR / "index.html"
    if html.exists():
        return html.read_text()
    return "<h1>meme-viewer: static/ missing</h1>"
