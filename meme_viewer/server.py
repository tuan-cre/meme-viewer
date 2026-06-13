from __future__ import annotations

import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

MEMES_DIR = Path.home() / ".local" / "share" / "memes"

GALLERY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meme Collection</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #050508;
    color: #c7a0c8;
    font-family: "Segoe UI", system-ui, sans-serif;
    padding: 20px;
  }
  h1 { font-size: 1.5rem; margin-bottom: 20px; color: #b48ead; }
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;
  }
  .item {
    background: #08080d;
    border-radius: 8px;
    overflow: hidden;
    transition: background 0.2s;
  }
  .item:hover { background: #0f0f18; }
  .item a {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-decoration: none;
    color: #c7a0c8;
  }
  .item img {
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
    display: block;
  }
  .item span {
    padding: 8px 10px;
    font-size: 0.85rem;
    text-align: center;
    word-break: break-all;
    width: 100%;
  }
  .full {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
  }
  .full img {
    max-width: 100%;
    max-height: 100vh;
    object-fit: contain;
    border-radius: 8px;
  }
  .back {
    position: fixed;
    top: 20px;
    left: 20px;
    background: #08080d;
    color: #b48ead;
    padding: 8px 16px;
    border-radius: 6px;
    text-decoration: none;
    font-size: 0.9rem;
    z-index: 10;
  }
  .back:hover { background: #1a1423; }
  @media (max-width: 480px) {
    .gallery { grid-template-columns: repeat(2, 1fr); gap: 8px; }
    body { padding: 10px; }
  }
</style>
</head>
<body>
{{CONTENT}}
</body>
</html>"""

INDEX_CONTENT = """<h1>Meme Collection</h1>
<div class="gallery">
{{ITEMS}}
</div>"""

ITEM_HTML = """<div class="item"><a href="/view/{name}"><img src="/images/{name}" loading="lazy"><span>{name}</span></a></div>"""

VIEW_HTML = """<a class="back" href="/">&larr; Back</a>
<div class="full"><img src="/images/{name}"></div>"""


class MemeGalleryHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves the meme gallery."""

    # Suppress default HTTP server logs
    def log_message(self, format: str, *args: object) -> None:
        pass

    def _serve_file(self, path: Path) -> None:
        ext = path.suffix.lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "application/octet-stream")
        try:
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self._serve_404()

    def _serve_404(self) -> None:
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not Found")

    def _gallery_page(self) -> str:
        exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        if MEMES_DIR.exists():
            files = sorted(
                p for p in MEMES_DIR.iterdir()
                if p.is_file() and p.suffix.lower() in exts
            )
        else:
            files = []
        items = "\n".join(ITEM_HTML.format(name=p.name) for p in files)
        body = INDEX_CONTENT.replace("{{ITEMS}}", items)
        return GALLERY_HTML.replace("{{CONTENT}}", body)

    def _view_page(self, name: str) -> str:
        body = VIEW_HTML.format(name=name)
        return GALLERY_HTML.replace("{{CONTENT}}", body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]  # Strip query params

        if path == "/":
            html = self._gallery_page()
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path.startswith("/view/"):
            name = path[6:]
            html = self._view_page(name)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        elif path.startswith("/images/"):
            name = path[8:]
            filepath = MEMES_DIR / name
            if filepath.exists() and filepath.is_file():
                self._serve_file(filepath)
            else:
                self._serve_404()

        else:
            self._serve_404()


class MemeServer:
    """Lightweight HTTP server serving the meme collection."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._url: str = ""

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def start(self) -> str:
        """Start the server on a background thread. Returns the access URL."""
        if self._server is not None:
            return self._url

        self._server = HTTPServer((self.host, self.port), MemeGalleryHandler)
        actual_port = self._server.server_address[1]
        self._url = f"http://{self._local_ip()}:{actual_port}"

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        return self._url

    def stop(self) -> None:
        """Stop the server."""
        if self._server is None:
            return
        self._thread = None
        self._server.shutdown()
        self._server = None
        self._url = ""

    @staticmethod
    def _local_ip() -> str:
        """Get the local network IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip
