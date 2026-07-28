# MediaConductor MCP Configuration & Quick Setup

Set up MediaConductor MCP server in seconds by copying and pasting the configuration into your preferred AI client.

---

## 🚀 Quick Setup (Copy & Paste)

### 1. Claude Desktop

**File Location:**
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json` (e.g. `C:\Users\YOUR_USERNAME\AppData\Roaming\Claude\claude_desktop_config.json`)
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

#### Option A: Source Checkout with `uv` (Recommended)

Replace `D:/MediaConductor` with the path to your checkout and `D:/MediaProjects` with your media workspace path (use forward slashes `/` for path compatibility):

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "uv",
      "args": [
        "--project",
        "D:/MediaConductor",
        "run",
        "--no-sync",
        "mediaconductor",
        "mcp",
        "--mode",
        "manga-video",
        "--allow-root",
        "D:/MediaProjects"
      ]
    }
  }
}
```

#### Option B: Direct Virtual Environment (Fastest & Most Reliable on Windows)

Skips `uv` dependency sync on launch to prevent Windows binary lock errors:

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "D:/MediaConductor/.venv/Scripts/mediaconductor.exe",
      "args": [
        "mcp",
        "--mode",
        "manga-video",
        "--allow-root",
        "D:/MediaProjects"
      ]
    }
  }
}
```
*(On macOS/Linux, change the command to `D:/MediaConductor/.venv/bin/mediaconductor`)*

#### Option C: Globally Installed `mediaconductor`

If `mediaconductor` is installed globally on your system `PATH`:

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "mediaconductor",
      "args": [
        "mcp",
        "--mode",
        "manga-video",
        "--allow-root",
        "D:/MediaProjects"
      ]
    }
  }
}
```

---

### 2. Antigravity / Cursor / VS Code / Windsurf / Roo Code / Cline

**File Location:**
- **Workspace-specific:** `.vscode/mcp.json` or `.cursor/mcp.json` in your project root
- **Global Settings:** Open your client's MCP configuration settings tab and paste the `media-conductor` object below.

#### Paste block:

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "uv",
      "args": [
        "--project",
        "D:/MediaConductor",
        "run",
        "--no-sync",
        "mediaconductor",
        "mcp",
        "--mode",
        "manga-video",
        "--allow-root",
        "D:/MediaProjects"
      ]
    }
  }
}
```

*(If adding to an existing `"mcpServers"` object, copy only the `"media-conductor": { ... }` block).*

---

### 3. Command-Line Registration (One-Liner)

#### Claude CLI:
```bash
claude mcp add media-conductor -- uv --project D:/MediaConductor run --no-sync mediaconductor mcp --allow-root D:/MediaProjects
```

#### Antigravity CLI (`agy`):
```bash
agy mcp add media-conductor -- uv --project D:/MediaConductor run --no-sync mediaconductor mcp --allow-root D:/MediaProjects
```

---

## ⚡ Preparation Step

Before starting the MCP server for the first time, sync the Python virtual environment once:

```bash
uv sync --project D:/MediaConductor
```

To verify the installation outside of an MCP client:

```bash
uv --project D:/MediaConductor run --no-sync mediaconductor modes --mode manga-video --json
```

---

## 📂 Multi-Workspace Configuration

To allow MediaConductor to access multiple folders, repeat the `--allow-root` flag in `args`:

```json
"args": [
  "--project", "D:/MediaConductor",
  "run", "--no-sync", "mediaconductor", "mcp",
  "--mode", "manga-video",
  "--allow-root", "D:/MediaProjects",
  "--allow-root", "E:/OtherMangaWorkspace"
]
```

---

## 📁 Where the server writes

Everything the server downloads or generates goes under one folder in the
workspace — `<workspace>/data/`:

```text
data/library/<Project>/   downloaded chapters, panels, narration, rights, reviews
data/audio/  data/audio_faded/   TTS takes and render-safe derivatives
data/output/<Project>/    item videos, <Project>_full.mp4, quality reports
data/review/  data/work/  review sheets; scratch and job logs
```

Deleting `data/` returns the workspace to a clean slate. The AI tool
environments, model caches and YouTube tokens live in `<install>/runtime/`
instead, so a fresh start never triggers a multi-gigabyte re-download, and
`bgm/` + `vocal/` stay outside too. Call the `where` tool for the resolved
`data_root` of the install you are connected to, and `workspace_layout` to
confirm nothing escaped.

`workspace-reset` is deliberately **not** an MCP tool — an irreversible
"delete every production" is not something a client should be able to trigger
by name. Run it from the CLI when you mean it.

---

## 🎙️ Configured voice and music

The narrator voice-clone reference and the music bed are set once in
`config.system.json`, so tool calls do not have to carry them:

```json
{
  "tts": { "engine": "auto", "speaker_wav": "D:/vocal/narrator.wav" },
  "bgm": { "file": "D:/music/theme.wav", "volume_db": -30 }
}
```

`run_full_pipeline` uses them whenever `speaker_wav` / `background_music` are
omitted, and `add_bgm` no longer requires `background_music` at all. Each value
accepts a **Windows absolute path** (`D:/vocal/n.wav`, `D:\vocal\n.wav`, UNC
shares), a **Linux absolute path** (`/home/me/vocal/n.wav`), or a path
**relative to `config.system.json` itself** — never relative to the server's
working directory, so one config resolves identically from any launcher.

Call the `doctor` tool and read its `media` block to confirm what resolved:
`speaker_wav`, `background_music` (the track actually found),
`background_music_source` (what you configured), and an `_exists` flag for
each. Both failures are silent otherwise — IndexTTS falls back to Kokoro
without a reference, and a video renders fine with no bed.

Configured defaults are still bound by `--allow-root`: a media file outside the
allowed roots is refused before the CLI is invoked.

---

## 🤖 LLM Self-Review & Agent Automation

The MediaConductor MCP server supports **complete autonomous LLM operation**:
- Reviews (`crop`, `narration`, `final-video`) are recorded via content hash-bound records, not boolean flags.
- An LLM agent performs the visual and narrative inspections itself, then records the approval using its agent identity via `manga_review`:

```json
{
  "tool": "manga_review",
  "arguments": {
    "action": "crop",
    "project_root": "D:/MediaProjects/data/library/Recap",
    "items": ["01"],
    "reviewer": "antigravity-agent"
  }
}
```

- Any subsequent change to source images, crops, or narration files automatically invalidates the review record.

---

## 🛠️ Troubleshooting: "Access is denied" on Windows

If launch fails with `Access is denied. (os error 5)` or `calling "initialize": EOF`:
- This occurs when `uv run` attempts to reinstall binaries while `mediaconductor.exe` is already running in the background.
- **Solution 1:** Always ensure `--no-sync` is included in your `uv run` arguments.
- **Solution 2:** Use the direct executable path (`.venv/Scripts/mediaconductor.exe`).
- **Solution 3:** Repair stale metadata once:
  ```powershell
  uv sync --project D:/MediaConductor --reinstall-package media-conductor
  ```

---

## 📋 Server Handshake & Capabilities

| Field | Value |
| --- | --- |
| `serverInfo.name` | `media-conductor` |
| `serverInfo.version` | Installed `mediaconductor` version |
| `protocolVersion` | `2025-11-25` (fallbacks: `2025-06-18`, `2024-11-05`) |
| Capabilities | `tools` only |
| Transport | stdio, newline-delimited JSON-RPC 2.0 |

---

## 🛠️ Complete MCP Tool Catalog (49 Tools)

The catalog exposes **49 tools** from `mediaconductor/command_spec.py`. Every tool call shells out to the CLI.

### Install & Environment (6)
| Tool | Required | Purpose |
| --- | --- | --- |
| `modes` | — | Show the manga-video catalog, dependencies, and MCP restart command. |
| `setup` | — | One-command provisioning: core binaries, AI tool envs, model downloads. Long-running. |
| `doctor` | — | Check ffmpeg/uv/git, GPU backend, installed AI tools, and the resolved `media` block (configured voice-clone WAV + music bed, each with an exists flag). |
| `where` | — | Resolved paths (`data_root` — the one deletable folder — plus `runtime_home` and `tools_home`) and version. |
| `workspace_layout` | — | Every resolved persistent root, and whether it stayed in `data/` (production) or `runtime/` (tool envs and caches). |
| `install_tool` | `name` | Install external AI env: `kokoro-82m`, `index-tts`, `magi-v3`, `deepseek-ocr2`. |

### Acquire & Crop (7)
| Tool | Required | Purpose |
| --- | --- | --- |
| `download` | — | Fetch MangaDex chapters politely and resumably. Long-running. |
| `style_detect` | `project_root` | Detect webtoon (`webtoon_split`) vs paged manga (`page_split`). |
| `webtoon_split` | `project_root` | Crop webtoon strips into panels. Exit 3 = unapproved crops. |
| `webtoon_cutcheck` | `project_root` | Review windows around forced cuts and short panels. |
| `webtoon_override` | `file`, `project_root` | Record merge/split crop fixes. |
| `page_split` | `project_root` | Crop paged manga with MAGI v3. Long-running. |
| `panels_remap` | `project_root` | Map archived panels to new crops after a re-split. |

### Narration (4)
| Tool | Required | Purpose |
| --- | --- | --- |
| `panel_transcript` | `project_root` | DeepSeek-OCR 2 pass into `transcript.json`. Long-running. |
| `narration_edit` | `project_root`, `item` | Upsert/delete `narration.json` or `intro.json` entries. |
| `narration_check` | `project_root` | Validate files parse, images exist, stems unique. |
| `narration_review_sheets` | `project_root` | Generate visual review sheets pairing panels and lines. |

### Review, Decisions & Rights (3)
| Tool | Required | Purpose |
| --- | --- | --- |
| `manga_review` | `action`, `project_root` | Record or check hash-bound reviews: `crop`, `narration`, `final-video`, `check`. |
| `panel_decisions` | `project_root` | Record panel omissions or audit unaccounted panels. |
| `manga_rights` | `action`, `project_root` | `init` / `check` / `show` the publication rights manifest. Fails closed. |

### Audio, Render & Join (7)
| Tool | Required | Purpose |
| --- | --- | --- |
| `video_check` | `project_root` | Pre-flight check: narration vs panels vs audio counts. |
| `audio_audit` | `project_root`, `audio_root` | Audit WAVs; `fix=true` deletes bad audio for regeneration. |
| `generate_audio` | `project_root`, `audio_root` | Kokoro TTS per panel. Long-running. |
| `render_videos` | `project_root`, `audio_root`, `output_root` | Render item videos from panels + audio. Long-running. |
| `build_long_video` | `project_root`, `output_root` | Join item videos into one long video. Long-running. |
| `add_bgm` | `project_root`, `output_root` | Mix background music into joined video. `background_music` is optional — defaults to `config.system.json` → `bgm.file`. |
| `run_full_pipeline` | `project_root`, `audio_root`, `output_root` | Complete pipeline: audio → fade → render → join/BGM/normalize → validate. `speaker_wav` and `background_music` default to `config.system.json` (`tts.speaker_wav`, `bgm.*`). Long-running. |

### Validation & QA (4)
| Tool | Required | Purpose |
| --- | --- | --- |
| `video_validate` | `project_root` | Validate stream formats, durations, counts against inputs. |
| `video_chapters` | `project_root`, `output_root` | Generate paste-ready YouTube chapter timestamps. |
| `video_quality` | `project_root`, `output_root` | Measure deliverable loudness, true peak, drift, black/frozen frames. |
| `work_qa` | `project_root` | Aggregated machine-checkable gate across all production stages. |

### Project State & Multi-Agent Coordination (8)
| Tool | Required | Purpose |
| --- | --- | --- |
| `library_list` | `project_root` | List projects and per-item readiness. |
| `series_plan` | `project_root` | Slice items into upload batches and identify next batch. |
| `series_mark_published` | `project_root`, `items`, `video_id` | Record uploaded batch in `publish.json`. |
| `work_status` | `project_root` | Stage dashboard and active agent claims/notes. |
| `work_claim` | `project_root` | Atomic TTL lease on items/resources for multi-agent work. |
| `work_note` | `project_root` | Append-only shared notebook for handoffs and cast notes. |
| `work_todo` | `project_root` | Shared session todo list for task planning. |
| `work_artifacts` | `project_root` | Inventory of reusable generated artifacts. |

### Thumbnail & Publishing (7)
| Tool | Required | Purpose |
| --- | --- | --- |
| `thumbnail_candidates` | `project_root` | Shortlist panels worth using as a thumbnail base + contact sheets. Ranking is a proposal — open and choose. |
| `thumbnail_compose` | `base`, `output` | Compose a 1280×720 thumbnail from approved panels: hook text, block arrows, speech bubbles, chapter badge. No image generation. |
| `title_check` | `titles` | Check recap titles against the house pattern (shape only — truthfulness is yours). |
| `youtube_profiles` | — | List YouTube account profiles and channel state. |
| `youtube_status` | — | Check profile status and refresh token. |
| `youtube_upload` | `project_root`, `video`, `title` | Resumable upload through YouTube profile. Long-running. |
| `youtube_list` | — | List profile's uploaded videos and IDs. |
| `youtube_delete` | `video_id` / `url` | Irreversibly delete YouTube video (`confirm=true`). |
| `youtube_thumbnail` | `video_id`, `image` | Set/replace thumbnail on YouTube video. |

### Background Jobs (3)
| Tool | Required | Purpose |
| --- | --- | --- |
| `job_start` | `tool` | Start a long-running tool as a detached background job. |
| `job_status` | `job_id` | Check background job progress, state, exit code, log tail. |
| `job_list` | — | List all active/past background jobs. |
