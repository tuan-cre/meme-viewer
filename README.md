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
meme-viewer            # native window (Dear PyGui, no browser)
```

No setup: memes live in `platformdirs.user_data_dir("memes")`
(`~/.local/share/memes` on Linux, `%LOCALAPPDATA%\memes` on Windows).

Copy needs a clipboard helper on Linux: `wl-copy` (Wayland) or `xclip`
(X11). Without one, the file path is copied instead.

Run without installing:
```sh
uv run --frozen meme-viewer
```

Launcher mode is the default (narrow, no preview): type to filter, click or
`Enter` copies and quits, `Esc` quits, `Ctrl+E` or the Expand button shows
the preview pane. `Ctrl+V` pastes an image straight from the clipboard into
the collection (screenshot → paste — no file dialog needed). The grid
reflows its columns as you resize. Mode is remembered;
`meme-viewer --full` forces full mode once.

Browser fallback: `meme-web` (same collection via localhost).

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
