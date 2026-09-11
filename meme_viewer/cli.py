"""CLI — local-first. `meme-viewer` browses your local collection.

The localhost server is an implementation detail (no config, no account).
LAN sharing via `meme-serve --share` is an opt-in bonus.
"""
from __future__ import annotations

import argparse
import webbrowser


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    from .server import app

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    p = argparse.ArgumentParser(description="Browse your local meme collection.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    import threading
    import time

    import uvicorn

    from .server import app

    threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": "127.0.0.1",  # local only — never exposed
            "port": args.port,
            "log_level": "warning",
        },
        daemon=True,
    ).start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Local memes at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def serve_main() -> None:
    p = argparse.ArgumentParser(description="Serve meme collection over HTTP (bonus).")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument(
        "--share",
        action="store_true",
        help="Expose on the LAN (0.0.0.0). Optional — local use needs nothing.",
    )
    args = p.parse_args()
    host = "0.0.0.0" if args.share else args.host
    print(f"Serving memes at http://{host}:{args.port}")
    serve(host=host, port=args.port)


if __name__ == "__main__":
    serve_main()
