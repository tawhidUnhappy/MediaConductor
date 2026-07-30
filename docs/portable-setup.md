# Portable, fully-isolated install

Everything mangaEasy needs lives in **one folder**. No system Python, no
system ffmpeg, no `PATH` entry, no registry key, nothing in `~/.cache`,
`~/.local`, `%LOCALAPPDATA%` or `/usr`. Delete the folder and the machine is
exactly as it was.

That is not how these tools behave by default — `uv` caches wheels in
`~/.cache/uv` and puts downloaded interpreters in `~/.local/share/uv/python`,
Hugging Face writes to `~/.cache/huggingface`, and torch/Triton/Inductor each
keep their own home-directory cache. Together that is tens of gigabytes in
places nobody remembers. So mangaEasy pins every one of them inside the
install folder instead.

Prefer a normal system-wide install? See [install.md](install.md).

---

## 1. One command

The bootstrap needs **only** bash + curl + tar (macOS/Linux) or Windows
PowerShell 5+ (Windows). It downloads a portable `uv`, a private Python, the
dependencies, and portable ffmpeg — all into the folder.

### macOS / Linux

```bash
git clone https://github.com/tawhidUnhappy/mangaEasy.git
cd mangaEasy
./bootstrap.sh
```

### Windows

```powershell
git clone https://github.com/tawhidUnhappy/mangaEasy.git
cd mangaEasy
powershell -ExecutionPolicy Bypass -File bootstrap.ps1
```

No git? Download the repo zip from GitHub, extract it, and run the same script
from inside the extracted folder.

Add `--with-tools` (bash) or `-WithTools` (PowerShell) to also install the AI
tool environments and model weights in the same run. That part is several
gigabytes, so it is opt-in; you can always do it later with
`uv run mangaeasy setup`.

Re-running is safe — every step is skipped when it is already done.

### Verify

```bash
uv run mangaeasy env --check     # exits non-zero if anything writes outside the folder
uv run mangaeasy where --json    # every resolved path
uv run mangaeasy doctor          # readiness, including an "Isolation" block
uv run mangaeasy smoke-test      # renders a real 2-second video end to end
```

`smoke-test` is the real proof: if it prints `SMOKE TEST PASS`, the install
works.

---

## 2. What ends up where

```
mangaEasy/                        ← delete this folder, and nothing remains
  .venv/                          the Python environment
  data/                           ← everything you download or generate
    library/<project>/            chapters, panels, narration, review records
    audio/ audio_faded/ output/   TTS takes, render derivatives, videos
    review/ work/                 review sheets, scratch, job logs
  runtime/                        ← machinery; survives a `workspace-reset`
    cache/uv/                     wheel cache          (was ~/.cache/uv)
    cache/uv_python/              the private Python    (was ~/.local/share/uv/python)
    cache/hf/                     model weights        (was ~/.cache/huggingface)
    cache/torch/ triton/ ...      compiler caches
    tools/<tool>/                 isolated AI tool envs (Kokoro, IndexTTS, MAGI, OCR)
    tools/_vendor/ffmpeg/bin/     portable ffmpeg + ffprobe
    tools/_vendor/uv/bin/         portable uv + uvx
    tools/_vendor/git-lfs/bin/    portable git-lfs
    state/ secrets/               install state, YouTube OAuth tokens
  bgm/ vocal/                     your own licensed music and narrator takes
```

Rough sizes: ~600 MB after `bootstrap.sh` (Python + wheels + ffmpeg), plus
several GB per AI tool env if you install them.

Two trees, and the split matters: `data/` is the deletable one
(`mangaeasy workspace-reset`), `runtime/` is the expensive one. A fresh start
should cost re-work, not an 80 GB re-download.

---

## 3. Running it afterwards

The launchers set the isolation environment for you:

```bash
./run.sh          # macOS/Linux  (or double-click run.command on macOS)
run.bat           # Windows
```

To use `uv` or `mangaeasy` directly in your own shell, export the same
environment first — otherwise `uv` falls back to its default cache in your home
directory:

```bash
cd /path/to/mangaEasy
eval "$(uv run mangaeasy env --sh)"      # bash/zsh
```

```powershell
cd C:\path\to\mangaEasy
uv run mangaeasy env --ps1 | Invoke-Expression
```

```bat
for /f "delims=" %i in ('uv run mangaeasy env --bat') do @%i
```

`mangaeasy env --json` gives the same values as one JSON object.

### Deliberately sharing a cache

Set `MANGAEASY_SHARE_CACHES=1` to let an ambient `HF_HOME`/`UV_CACHE_DIR` win —
useful when several checkouts should share one model cache. The install is then
**not** self-contained, and `doctor` says so.

---

## 4. Manual / offline install

For a machine with no outbound access to GitHub releases, or where you want to
review each binary before it runs. Ask the install for the exact URLs and
digests for your platform:

```bash
mangaeasy tool-downloads             # this machine
mangaeasy tool-downloads --all       # every platform
mangaeasy tool-downloads --json      # machine-readable
```

That command is generated from the same table the downloader verifies against,
so the links below cannot drift from what the code actually fetches.

### Portable uv 0.11.16

| OS / arch | Download | SHA-256 |
|---|---|---|
| Linux x64 | [uv-x86_64-unknown-linux-gnu.tar.gz](https://github.com/astral-sh/uv/releases/download/0.11.16/uv-x86_64-unknown-linux-gnu.tar.gz) | `74947fe2c03315cf07e82ab3acc703eddef01aba4d5232a98e4c6825ec116131` |
| Linux arm64 | [uv-aarch64-unknown-linux-gnu.tar.gz](https://github.com/astral-sh/uv/releases/download/0.11.16/uv-aarch64-unknown-linux-gnu.tar.gz) | `8c9d0f0ee98166ae6ab198747519ba6f25db29d185bd2ae5960ecebc91a5c22a` |
| macOS arm64 | [uv-aarch64-apple-darwin.tar.gz](https://github.com/astral-sh/uv/releases/download/0.11.16/uv-aarch64-apple-darwin.tar.gz) | `2b25be1af546be330b340b0a76b99f989daa6d92678fdffb87438e661e9d88fb` |
| macOS x64 | [uv-x86_64-apple-darwin.tar.gz](https://github.com/astral-sh/uv/releases/download/0.11.16/uv-x86_64-apple-darwin.tar.gz) | `6b91ae3de155f51bd1f5b74814821c79f016a176561f252cd9ddfb976939af2e` |
| Windows x64 | [uv-x86_64-pc-windows-msvc.zip](https://github.com/astral-sh/uv/releases/download/0.11.16/uv-x86_64-pc-windows-msvc.zip) | `dd9d6d6554bfab265bfa98aa8e8a406c5c3a7b97582f93de1f4d48d9154a0395` |

Extract `uv` and `uvx` into `runtime/tools/_vendor/uv/bin/`.

### Portable git-lfs 3.7.1

| OS / arch | Download | SHA-256 |
|---|---|---|
| Linux x64 | [git-lfs-linux-amd64-v3.7.1.tar.gz](https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-linux-amd64-v3.7.1.tar.gz) | `1c0b6ee5200ca708c5cebebb18fdeb0e1c98f1af5c1a9cba205a4c0ab5a5ec08` |
| Linux arm64 | [git-lfs-linux-arm64-v3.7.1.tar.gz](https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-linux-arm64-v3.7.1.tar.gz) | `73a9c90eeb4312133a63c3eaee0c38c019ea7bfa0953d174809d25b18588dd8d` |
| macOS arm64 | [git-lfs-darwin-arm64-v3.7.1.zip](https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-darwin-arm64-v3.7.1.zip) | `76260fb34f4ee622ff0a66b857e5954aa49c7e343a92e57a1ec4a760618c94b2` |
| macOS x64 | [git-lfs-darwin-amd64-v3.7.1.zip](https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-darwin-amd64-v3.7.1.zip) | `b5b1b641c0648c83661fa9eda991cd3eff945264dabc2cdf411a80dfe7ec0970` |
| Windows x64 | [git-lfs-windows-amd64-v3.7.1.zip](https://github.com/git-lfs/git-lfs/releases/download/v3.7.1/git-lfs-windows-amd64-v3.7.1.zip) | `8683cdc3d6c029b49393dcebbaa6265bd6efd9abdcf837be855b4cd42e5e80b6` |

Extract `git-lfs` (or `git-lfs.exe`) into `runtime/tools/_vendor/git-lfs/bin/`.

### Portable ffmpeg

These are rolling builds, so the digest is not pinned here — `bootstrap-tools`
verifies each download against the checksum manifest the provider publishes
alongside it. The macOS provider publishes none, so prefer a trusted system
ffmpeg there if that matters to you.

| OS / arch | Download | Extract |
|---|---|---|
| Linux x64 | [ffmpeg-master-latest-linux64-gpl.tar.xz](https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz) | `bin/ffmpeg`, `bin/ffprobe` |
| Linux arm64 | [ffmpeg-master-latest-linuxarm64-gpl.tar.xz](https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz) | `bin/ffmpeg`, `bin/ffprobe` |
| Windows x64 | [ffmpeg-master-latest-win64-gpl.zip](https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip) | `bin/ffmpeg.exe`, `bin/ffprobe.exe` |
| macOS arm64 | [ffmpeg.zip](https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip) + [ffprobe.zip](https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip) | `ffmpeg`, `ffprobe` |
| macOS x64 | [ffmpeg.zip](https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip) + [ffprobe.zip](https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffprobe.zip) | `ffmpeg`, `ffprobe` |

Extract into `runtime/tools/_vendor/ffmpeg/bin/` and `chmod +x` them on
macOS/Linux.

### Then finish by hand

```bash
export MANGAEASY_INSTALL_ROOT="$PWD"
. scripts/isolate.sh                 # pins the caches; must precede uv
uv python install 3.12
uv sync --python 3.12
uv run mangaeasy env --check
```

`scripts/isolate.sh` (and `scripts/isolate.cmd`) must be sourced **before**
`uv`: `uv sync` is what downloads the interpreter and every wheel, so by the
time any mangaEasy Python code could redirect the cache, uv has already written
a few hundred MB to your home directory.

---

## 5. For an AI agent

A deterministic procedure. Every command prints JSON or a clear pass/fail, and
none of them prompts on stdin.

```bash
# 1. Bootstrap (idempotent). Non-zero exit = stop and report the output.
cd <install-root>
./bootstrap.sh                       # Windows: powershell -ExecutionPolicy Bypass -File bootstrap.ps1

# 2. Confirm isolation. Non-zero exit means something writes outside the folder;
#    the offending variables are printed on stderr.
uv run mangaeasy env --check

# 3. Read the resolved layout instead of guessing at paths.
uv run mangaeasy where --json        # .isolated, .data_root, .caches, .escaping
uv run mangaeasy doctor --json       # .isolated, .executables, .tools, .gpu_backend

# 4. Prove it renders.
uv run mangaeasy smoke-test          # exit 0 + MANGAEASY_RESULT {... "ok": true}

# 5. Only if AI tool envs are needed (several GB; run as a background job).
uv run mangaeasy setup --mode manga-video
```

Rules that matter:

- **Never** run bare `uv`/`pip`/`huggingface-cli` without sourcing
  `scripts/isolate.sh` first — that is how downloads escape the folder.
- Get paths from `where --json`, never by string-joining your own.
- `tool-downloads --json` gives URLs + digests if you must fetch binaries
  yourself; verify the SHA-256 before executing anything.
- Long steps (`setup`, `install-tool`) belong in `mangaeasy job-start`, not a
  blocking call.
- Exit codes: `0` ok, `1` failure, `2` bad CLI use, `3` artifact created but a
  review gate is unmet.

---

## 6. Troubleshooting

**`doctor` reports paths outside the install folder.** You are in a shell that
never sourced the isolation environment. Run `eval "$(uv run mangaeasy env --sh)"`,
or use `./run.sh`. If `MANGAEASY_SHARE_CACHES` is set, unset it.

**`bootstrap.sh` aborts on a SHA-256 mismatch.** Refusing is correct — the
download was truncated or tampered with. Retry; if it repeats, compare against
`mangaeasy tool-downloads --json` and check whether a proxy is rewriting the
response.

**Renders are slow and mention an unusable encoder.** A hardware encoder is
compiled into ffmpeg but cannot open on this machine — commonly a driver too
old for the rolling build's NVENC API, a GPU without encode silicon, or a
container that does not map the encode libraries. mangaEasy probes each
candidate and falls back to libx264, which is correct but CPU-bound. Update the
GPU driver to fix the speed.

**`uv` is not found after bootstrap.** The portable copy lives in
`runtime/tools/_vendor/uv/bin/` and is only on `PATH` inside `run.sh`/`run.bat`
or after sourcing `scripts/isolate.sh`. This is deliberate: nothing is added to
your shell profile.

**Moving the install.** Move the whole folder; paths are resolved relative to it
at runtime. Only `.venv/` is location-sensitive — re-run `./run.sh` (or
`uv sync`) after moving and it is rebuilt from the folder-local cache.

---

## Related

- [install.md](install.md) — normal system-wide install paths
- [setup.md](setup.md) — what `setup` provisions, and per-tool detail
- [external-tools.md](external-tools.md) — the isolated AI tool environments
- [ai-guide.md](ai-guide.md) — the CLI/MCP contract for agents
