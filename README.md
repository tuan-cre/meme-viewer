# meme-viewer

Minimal web viewer for meme collections. Linux + Windows. One backend, one UI in the browser.

## Install `uv`

Linux:
```sh
curl -LsSf astral.sh/uv/install.sh | sh
```

Windows (PowerShell):
```powershell
irm astral.sh/uv/install.ps1 | iex
```

## Run (no install)

```sh
uv run --frozen meme-serve
# custom port: uv run --frozen meme-serve --port 9000
```

Then open http://127.0.0.1:8765.

## Install as a tool

```sh
uv tool install .
meme-serve
meme-viewer   # serves + opens the browser
```

Update later with `uv tool upgrade meme-viewer`.

## Dev

```sh
uv sync
uv run meme-serve --port 8765
```

Memes live in `platformdirs.user_data_dir("memes")`
(`~/.local/share/memes` on Linux, `%LOCALAPPDATA%\memes` on Windows).
