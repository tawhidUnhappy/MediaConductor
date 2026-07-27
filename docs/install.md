# Installing MediaConductor

MediaConductor is a CLI and MCP server for manga, manhwa, and webtoon recap
video production. These are the three supported installation paths.

---

## Option 1 — Install with uv (recommended)

Requires [uv](https://docs.astral.sh/uv/) installed on your system.

```bash
uv tool install git+https://github.com/tawhidUnhappy/MediaConductor.git
mediaconductor --version
```

This puts `mediaconductor` on your `PATH`. The legacy `mangaeasy` alias is also
installed for existing automation. Update later:

```bash
uv tool upgrade media-conductor
```

Run without installing (useful for a quick test):

```bash
uvx --from git+https://github.com/tawhidUnhappy/MediaConductor.git mediaconductor --help
```

---

## Option 2 — Download a frozen release (no Python needed)

The [**Releases page**](https://github.com/tawhidUnhappy/MediaConductor/releases/latest)
ships a self-contained frozen build of the CLI per platform:

| Platform | File | Run |
|---|---|---|
| Windows | `media-conductor-windows.zip` | unzip → `MediaConductor\mediaconductor.exe --help` |
| macOS (Apple Silicon) | `media-conductor-macos-arm64.zip` | unzip → `xattr -cr MediaConductor.app` once → `MediaConductor.app/Contents/MacOS/mediaconductor --help` |
| Linux | `media-conductor-linux.tar.gz` | `tar xzf` → `MediaConductor/mediaconductor --help` |

No system Python is required — the build bundles it. The archives are unsigned
(free software, no paid certificate): on Windows SmartScreen click **More
info → Run anyway**; on macOS run the `xattr -cr` line above once.

---

## Option 3 — From source (contributors)

```bash
git clone https://github.com/tawhidUnhappy/MediaConductor.git
cd MediaConductor
uv sync
uv run mediaconductor --help
```

Or run `./run.sh` (macOS/Linux) / `run.bat` (Windows) from the repo root — it
runs `uv sync` and prints the command list. New to the code? Open
[CLAUDE.md](../CLAUDE.md).

Build a frozen release yourself with PyInstaller:

```bash
uv sync --group dev
uv run pyinstaller packaging/mediaconductor.spec
# Output: dist/MediaConductor/ (Windows/Linux) or dist/MediaConductor.app/ (macOS)
```

---

## First-run setup

Install the isolated dependencies (details in [setup.md](setup.md)):

```bash
mediaconductor modes
mediaconductor setup --mode manga-video
```

It vendors the core binaries (ffmpeg/uv/git-lfs), then installs the AI tool
envs + models that fit the machine: Kokoro TTS always; IndexTTS, MAGI v3, and
DeepSeek-OCR 2 when an NVIDIA GPU is present. `--minimal`, `--all`,
`--skip <tool>`, `--dry-run` variants; safe to re-run (resumes).

Prefer picking pieces yourself?

```bash
mediaconductor doctor --mode manga-video --json
mediaconductor bootstrap-tools
mediaconductor install-tool kokoro-82m
mediaconductor install-tool index-tts
mediaconductor install-tool magi-v3
```

Everything MediaConductor writes stays inside the install — nothing is
scattered across the system. GPU acceleration (NVIDIA CUDA / Apple Silicon) is
detected automatically. Core video tools and selected models support CPU
fallback; GPU-only or impractically slow tools are reported by `doctor` for the
chosen mode.

### Where your data lives

Two folders, and the split is deliberate:

| Folder | Holds | Deleting it |
|---|---|---|
| `<install>/data/` | every downloaded chapter, panel, narration, WAV, render, review sheet and job log | **the supported fresh start** (`mediaconductor workspace-reset`) — costs re-work, nothing else |
| `<install>/runtime/` | AI tool envs, HF/torch/uv caches, install state, YouTube tokens | costs a multi-gigabyte re-download; recover with `mediaconductor setup` |

Your `bgm/`, `vocal/` and config files sit beside both and are never written
by MediaConductor, so a reset cannot take them with it. Check where a given
install actually resolved them with `mediaconductor where --json` /
`mediaconductor workspace-layout`.

`<install>` is the repo root in a source checkout. For a frozen build it is the
folder holding the executable, unless that location is read-only:

| Platform | `<install>` for a frozen build (when `MEDIACONDUCTOR_ROOT` is unset) |
|---|---|
| Windows | next to the exe |
| macOS | next to the exe, or `~/Library/Application Support/mangaEasy` inside a sealed `.app` |
| Linux | next to the exe, or `~/.local/share/mangaEasy` when that is read-only (AppImage, `/opt`) |

`MEDIACONDUCTOR_ROOT` moves the whole install root. To move just one tree,
use `MEDIACONDUCTOR_DATA_ROOT` (productions — e.g. onto a larger drive) or
`MEDIACONDUCTOR_HOME` (tool envs and caches — e.g. shared between checkouts);
point those at *different* trees, since a reset of one must not delete the
other.

---

## Updating

- **uv install**: `uv tool upgrade media-conductor`.
- **Frozen release**: download the newer archive and replace the old one; your
  data folder is separate, so installed tools/projects carry over.
- **Source**: `git pull && uv sync`.
