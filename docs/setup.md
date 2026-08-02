# Setup — from a fresh clone to a verified install

The short version, for a machine that already has `git` and `uv`:

```bash
git clone https://github.com/tawhidUnhappy/mangaEasy.git
cd mangaEasy
uv sync
uv run mangaeasy setup --mode manga-video
uv run mangaeasy smoke-test     # proves the install actually produces video
```

(Installed via `uv tool install` or a frozen release instead? Just run
`mangaeasy setup --mode <mode>` then `mangaeasy smoke-test`.)

The rest of this page is the **agent runbook**: the exact sequence an LLM
agent follows on a machine it has never seen, with a machine-checkable
verification step after each stage and a troubleshooting table of real
failures. Every command is non-interactive and safe to re-run.

---

## Agent runbook

### Step 0 — Prerequisites (`git`, `uv`)

Only two host tools are needed; everything else (Python included — `uv`
downloads and pins its own interpreter) is provisioned into the repo folder.

```bash
git --version || echo MISSING git
uv --version  || echo MISSING uv
```

Install `uv` if missing:

| Platform | Command |
|---|---|
| Windows (PowerShell) | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` |
| Windows (winget) | `winget install astral-sh.uv` |
| macOS / Linux | `curl -LsSf https://astral.sh/uv/install.sh | sh` |

After installing, open a fresh shell (or add `~/.local/bin` to PATH) and
re-check `uv --version`. `git` comes from the platform package manager
(`winget install Git.Git`, `apt install git`, Xcode CLT on macOS).

> **Windows note:** never invoke bare `python` — on many machines it is the
> Microsoft Store stub that opens a browser. Always go through
> `uv run mangaeasy ...` / `uv run python ...`.

### Step 1 — Clone and sync the Python environment

```bash
git clone https://github.com/tawhidUnhappy/mangaEasy.git
cd mangaEasy
uv sync
```

`uv sync` creates `.venv/` from the committed lockfile (interpreter
included). Verify:

```bash
uv run mangaeasy --version
uv run mangaeasy where --json     # resolved data/tool paths for THIS install
```

**Run every subsequent command from the repo root.** Two roots are resolved
per install: `data/` (everything downloaded or generated —
`data/library/`, `data/audio/`, `data/audio_faded/`, `data/output/`,
`data/review/`, `data/work/`) and `runtime/` (tool envs, caches, state,
OAuth tokens). Running from elsewhere is the classic "Failed to spawn:
mangaeasy" / wrong-paths failure. `setup` registers this workspace so a
command started from the wrong directory still resolves back here, and
`mangaeasy workspace-layout` shows exactly where each root landed.

### Step 2 — Provision binaries, tool envs and models

```bash
uv run mangaeasy setup --mode manga-video
```

GPU-aware and profile-driven — what gets installed, in order:

1. **Core binaries** — ffmpeg/ffprobe, uv, git-lfs, vendored into this
   install's own tools dir (~100 MB). uv and Git LFS are version- and
   SHA-256-pinned; Windows/Linux FFmpeg is checked against the publisher's
   checksum manifest. On macOS, prefer a trusted system FFmpeg because that
   bootstrap provider does not publish archive checksums. Nothing goes
   system-wide.
2. **Hardware detection** — NVIDIA GPU check picks the profile.
3. **AI tool environments** — each in its own isolated `uv` env under
   `runtime/tools/`, models included. Sizes below are **on-disk after
   install**, measured on a real Windows/CUDA run — each env carries its own
   torch build, which is why a "small" model still costs gigabytes:

   | Tool env | Installed when | Role | On disk |
   |---|---|---|---|
   | `kokoro-82m` | always | CPU TTS (universal fallback voice) | 4.5 GB |
   | `index-tts` | NVIDIA GPU | voice-cloning TTS (the recap voice) | 10.6 GB |
   | `magi-v3` | NVIDIA GPU | panel detection for paged manga | 4.3 GB |
   | `deepseek-ocr2` | NVIDIA GPU | panel OCR (`panel-transcript`) | 10.6 GB |

4. **Readiness report** — the same data as `mangaeasy doctor --json`, plus
   a `MANGAEASY_RESULT` line with per-tool ok/failed status.

**Free disk needed: ~50 GB** for the full GPU profile — 30 GB of tool envs
plus ~17 GB of `uv` build cache under `runtime/cache/uv/`. The cache is pure
scratch once the envs exist; `uv cache prune` reclaims most of it without
touching an installed tool. The CPU profile (Kokoro only) needs ~10 GB.

Useful variants:

```bash
mangaeasy setup --mode manga-video --dry-run  # inspect the exact plan
mangaeasy setup --minimal                     # core binaries only (fast)
mangaeasy setup --all                         # every cataloged tool, GPU or not
mangaeasy setup --mode manga-video --skip deepseek-ocr2  # repeatable skip
mangaeasy setup --mode manga-video --skip-models         # envs now, weights later
mangaeasy setup --mode manga-video --cpu  # or --cuda to force the torch target
```

Expect the full GPU profile to take tens of minutes on a fast connection —
it is **idempotent and resumable**: if the run is interrupted (network,
power), just rerun the same mode command; it skips what's done and resumes
partial model downloads. One tool failing does not abort the others (exit
code 1 + a named failure in the summary — fix with another `setup` run or
`mangaeasy install-tool <name>`; per-tool options live in
[install-tools.md](install-tools.md)).

### Step 3 — Verify with `doctor --json` (the machine contract)

```bash
uv run mangaeasy doctor --json
```

One JSON object. Assert, for the profile you installed:

- `executables.ffmpeg` and `executables.ffprobe` are non-null paths;
  `executables.uv` non-null.
- `gpu` / `cuda` reflect the hardware you expect (`cuda_device` names the
  card); `gpu_backend` is `cuda`, `mps`, or `cpu`.
- For each tool you installed: `tools.<name>.installed == true`
  (`configured` true means the catalog entry itself is valid).

Anything false → re-run `mangaeasy setup` (or `mangaeasy install-tool
<name>` for one tool) and check again. `doctor` is read-only and cheap; use
it as the fix-loop oracle.

### Step 4 — Prove it end to end with `smoke-test`

```bash
uv run mangaeasy smoke-test
```

Builds a tiny throwaway project (two generated panels + narration),
synthesizes silent audio with ffmpeg, renders a real MP4 through the actual
pipeline (encoder autodetection included — NVENC on NVIDIA, libx264
otherwise), ffprobes the result (h264 + aac, expected duration) and cleans
up after itself. `SMOKE TEST PASS` + exit 0 means this machine can produce
videos. `doctor` says the parts are installed; this proves they work
together.

Optionally prove the TTS toolchain too (downloads the Kokoro model on first
use if `--skip-models` was used):

```bash
uv run mangaeasy smoke-test --tts kokoro
```

`--keep` leaves `data/work/smoke_test/` behind for inspection on failure.

### Step 5 — Optional per-channel assets (not in the repo)

Nothing below is required — the pipeline runs without them — but recaps
produced for a real channel usually want:

- **A narrator voice and a music bed.** Copy `config.system.example.json` to
  `config.system.json` and set two paths — see the
  [config reference](#config-reference) below for every setting:

  ```json
  {
    "tts": { "engine": "auto", "speaker_wav": "D:/vocal/narrator.wav" },
    "bgm": { "file": "D:/music/theme.wav", "volume_db": -30 }
  }
  ```

  Both fail *silently* when unset or wrong: IndexTTS drops to Kokoro and the
  bed just goes missing, and both look like success until you listen. Check
  what resolved before a long render depends on it:

  ```bash
  mangaeasy doctor     # "Configured media" — the path, and whether it exists
  ```

- **YouTube upload**: place one downloaded Desktop-app client JSON at the
  `shared_client_file` reported by `mangaeasy youtube-profiles --json`.
  Each named profile keeps its own token/channel; the first live status/upload
  opens browser consent automatically for the channel owner and continues.
  Use `--no-auto-auth` only for a pre-authorized headless worker. See
  [youtube.md](youtube.md).
- **Config files**: none are needed to start. `config.system.json` (copy of
  `config.system.example.json`) holds machine-wide defaults; `config.json`
  holds per-project download defaults — if you copy the example, leave
  `download.name` null: a non-null name there silently overrides the
  project name `download --url` derives from the manga title (the CLI
  prints an `[INFO]` when that happens; agents should pass `--name`
  explicitly instead).

### Config reference

`config.system.json` holds machine-wide defaults. **Every setting is
optional** — the file itself is optional, and the values below are the
defaults. These are all of them; nothing else in the file is read.

| Setting | Default | What it does |
|---|---|---|
| `tts.engine` | `"auto"` | `auto` (IndexTTS when GPU + model + `speaker_wav` are all present, else Kokoro), or force `indextts` / `kokoro`. |
| `tts.speaker_wav` | `null` | Voice-clone reference for IndexTTS: a clean 10–30 s sample of the narrator. Ignored by Kokoro, which has a fixed voice. |
| `bgm.file` | `null` | The music bed. Unset means the video renders with no music. |
| `bgm.volume_db` | `-30` | How far the bed sits **below** the measured narration loudness. Keep within −20…−32. |
| `download_defaults.translated_language` | `"en"` | MangaDex translation language. |
| `download_defaults.use_data_saver` | ignored | Deprecated. mangaEasy always downloads original-quality MangaDex images for production. |
| `download_defaults.download_delay` | `0.5` | Seconds between image downloads. **Leave it alone** — the spacing is MangaDex politeness, not a speed knob. |
| `manga_video.audio_source` | `"faded"` | `faded` uses the 8 ms edge-faded derivatives (raw clip edges click). `raw` is a diagnostic override. |
| `manga_video.audio_fade_ms` | `8.0` | Length of those edge fades. |
| `cut_page.reading_direction` | `"rtl"` | Panel order fallback, used only when the source language is unknown; `download` normally records it in `manga.json`. |
| `paths.library_subdir` | `"library"` | Renames `data/library/`. |
| `paths.panels_subdir` | `"panels"` | Renames the per-chapter panel folder. |
| `paths.audio_subdir` | `"audio"` | Renames the per-chapter audio folder. |

**The two media paths** (`tts.speaker_wav`, `bgm.file`) are each **one exact
file you name** — nothing is auto-discovered, and unset means unset. Each
accepts:

- a **Windows absolute path** — `D:/vocal/n.wav`, `D:\vocal\n.wav`, or a UNC share `\\nas\music\n.wav`;
- a **Linux absolute path** — `/home/me/vocal/n.wav`;
- a path **relative to `config.system.json` itself** — `vocal/n.wav`, never
  relative to the current directory, so one config works from any cwd.

Both take **any mainstream audio format**: wav, mp3, m4a, aac, flac, ogg,
opus, wma, aiff, and anything else ffmpeg reads. A non-WAV voice reference is
transcoded to PCM once and cached, because IndexTTS decodes the prompt
through librosa/torchaudio and their codec support varies by machine.

`--speaker-wav` / `--background-music` override the configured values per run.

Render settings (resolution, fps, encoder, background style, blur) are **CLI
flags** on `mangaeasy video` / `video-render`, not config keys.

### Fix loop summary

| Symptom | Fix |
|---|---|
| `uv: command not found` | Step 0 install, then open a fresh shell |
| `Failed to spawn: mangaeasy` | you left the repo root — `cd` back before `uv run` |
| `doctor` shows a tool `installed: false` | `mangaeasy install-tool <name>` or re-run `setup` |
| model download interrupted / partial | re-run `mangaeasy setup` (resumes). A Hugging Face `CAS Client Error` / `error decoding response body` mid-download is a transient transfer failure, not a broken install — `doctor` names the missing file and the re-run fetches just that |
| `ffmpeg not found` in smoke-test | `mangaeasy bootstrap-tools`, re-check `doctor` |
| GPU expected but `cuda: false` | check `nvidia-smi` works on the host; fix drivers, re-run `setup --cuda` |
| no GPU at all | fine — CPU profile: TTS = Kokoro, encoding = libx264; `page-split` needs `setup --all` and is slow on CPU |
| disk pressure | `--skip deepseek-ocr2` saves ~10.6 GB, `--skip index-tts` ~10.6 GB; `--skip-models` defers model weights; `uv cache prune` reclaims most of `runtime/cache/uv/` afterwards |
| corporate proxy blocks Hugging Face | set `HTTPS_PROXY` before `setup`; caches stay in-tree (`runtime/`) |

### Where everything lands

Self-contained by design, in two folders:

| Folder | Holds | Deleting it |
|---|---|---|
| `data/` | every downloaded chapter, panel, narration, WAV, render, review sheet and job log | **the supported fresh start** — costs re-work, nothing else |
| `runtime/` | tool envs, HF/torch/uv caches, install state, YouTube tokens | costs an ~80 GB re-download; recover with `setup` |

HF/torch/uv caches are force-pinned under `runtime/cache/` — a global
`HF_HOME` will NOT leak downloads elsewhere; set
`MANGAEASY_SHARE_CACHES=1` if you want shared caches, see
[external-tools.md](external-tools.md).

Your `bgm/`, `vocal/` and config files sit beside both and are never written
by mangaEasy, so a reset cannot take them with it.

```bash
mangaeasy workspace-layout         # where each root actually resolved
mangaeasy workspace-reset          # dry run: what a fresh start would clear
mangaeasy workspace-reset --confirm
```

`MANGAEASY_DATA_ROOT` relocates `data/` (e.g. onto a larger drive) and
`MANGAEASY_HOME` relocates `runtime/` (e.g. to share one tool tree
between checkouts). Point them at *different* trees — `workspace-layout`
reports an overlap as an error, because a reset would otherwise delete the
tool environments.

### After setup

- Producing a recap as an agent: follow
  [.claude/skills/manga-recap/SKILL.md](../.claude/skills/manga-recap/SKILL.md)
  (Claude Code loads it automatically) or
  [recap-video-playbook.md](recap-video-playbook.md).
- CLI contract and full command catalog:
  [ai-guide.md](ai-guide.md) / `mangaeasy commands --json`.
