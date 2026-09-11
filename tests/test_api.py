"""API smoke tests — full upload/rename/trash roundtrip."""
from __future__ import annotations

import io
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from meme_viewer import core
from meme_viewer.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "memes_dir", lambda: tmp_path)
    for name in ("alpha.png", "beta.jpg"):
        Image.new("RGB", (50, 50), (0, 255, 0)).save(tmp_path / name)
    return TestClient(app)


def test_list_and_search(client):
    assert client.get("/api/memes").json() == ["alpha.png", "beta.jpg"]
    assert client.get("/api/memes", params={"q": "ALP"}).json() == ["alpha.png"]


def test_image_and_thumb(client):
    assert client.get(f"/images/{quote('alpha.png')}").status_code == 200
    r = client.get(f"/thumb/{quote('alpha.png')}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_traversal_blocked(client):
    assert client.get("/images/../secret").status_code == 404
    assert client.get("/images/%2e%2e%2fsecret").status_code == 404
    assert client.get("/thumb/%2e%2e%2fx").status_code == 404


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Search memes" in r.text


def test_rejects_bad_upload(client):
    r = client.post("/upload", files={"files": ("evil.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_roundtrip_upload_rename_trash(client):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, "PNG")
    buf.seek(0)
    saved = client.post(
        "/upload", files={"files": ("__t.png", buf, "image/png")}
    ).json()[0]
    assert saved == "__t.png"

    renamed = client.post(
        "/api/rename", json={"old": saved, "new": "__t2"}
    ).json()["filename"]
    assert renamed == "__t2.png"

    assert client.post("/api/trash", json={"name": renamed}).status_code == 200
    assert client.get(f"/images/{quote(renamed)}").status_code == 404


def test_rename_conflict(client):
    r = client.post("/api/rename", json={"old": "alpha.png", "new": "beta.jpg"})
    assert r.status_code == 400
