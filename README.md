# meme-viewer

Local-first viewer for your meme collection. Linux + Windows. Opens in the browser, works offline, zero config.

## Install `uv`

Linux:
```sh
curl -LsSf astral.sh/uv/install.sh | sh
```

Windows (PowerShell):
```powershell
irm astral.sh/uv/install.ps1 | iex
```

## Local use (the app)

```sh
uv tool install .
meme-viewer            # opens your local collection in the browser
```

No setup: memes live in `platformdirs.user_data_dir("memes")`
(`~/.local/share/memes` on Linux, `%LOCALAPPDATA%\memes` on Windows).
The localhost server is just plumbing — it binds `127.0.0.1`, never exposed.

Run without installing:
```sh
uv run --frozen meme-viewer
```

## Bonus: share on the LAN (optional)

Other devices just open the URL in their browser — no client mode needed.

```sh
meme-serve --share --port 8765
# or without install: uv run --frozen meme-serve --share
```

Local-only serve: `meme-serve` (binds `127.0.0.1`).

## Dev

```sh
uv sync
uv run meme-viewer --port 8765
```
