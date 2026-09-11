"""CLI — `meme-viewer` opens browser + serves, `meme-serve` serves only."""
from __future__ import annotations

import argparse
import webbrowser


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    from .server import app

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    import threading

    import uvicorn

    from .server import app

    threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": "127.0.0.1", "port": 8765, "log_level": "warning"},
        daemon=True,
    ).start()
    webbrowser.open("http://127.0.0.1:8765")
    # Keep alive: uvicorn runs in thread, block main thread
    import time

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def serve_main() -> None:
    p = argparse.ArgumentParser(description="Serve meme collection over HTTP.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    print(f"Serving memes at http://{args.host}:{args.port}")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    serve_main()
