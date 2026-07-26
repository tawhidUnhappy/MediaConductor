# MediaConductor MCP configuration

The examples below run the source checkout at `D:/MediaConductor` and allow it
to access media only under `D:/MediaProjects`.

Before registering the server, prepare the checkout once:

```powershell
uv sync --project D:/MediaConductor
```

## Complete `mcpServers` block

Copy this into a JSON-based MCP client configuration:

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

`--no-sync` matters on Windows: without it every client launch re-checks and
may reinstall the project, which rewrites `.venv/Scripts/mediaconductor.exe` —
and Windows refuses to replace that file while any server started from it is
still running. See [Startup fails with "Access is
denied"](#startup-fails-with-access-is-denied).

If the configuration file already has an `mcpServers` object, copy only this
entry inside it:

```json
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
```

Change `D:/MediaProjects` to the directory that contains the media projects
the server should be allowed to use. Forward slashes keep Windows paths valid
JSON without double escaping.

`--mode manga-video` is accepted for client-config compatibility and is the
default; `manga-video` is the only catalog. There is no router mode and no
`--all-tools` escape hatch — a tool outside the catalog answers *unknown*.

To allow a second intentional workspace, repeat both arguments:

```json
"--allow-root", "D:/MediaProjects",
"--allow-root", "E:/SharedMedia"
```

Restart the MCP client after changing the checkout path or allowed roots.

## Globally installed command

If `mediaconductor` is installed globally and available on `PATH`, the shorter
entry is:

```json
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
```

## Checkout executable, no launcher

The most robust entry for a checkout skips `uv` at launch entirely and runs the
venv's own console script, so starting a server can never rebuild or reinstall
anything:

```json
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
```

On Linux and macOS the path is `D:/MediaConductor/.venv/bin/mediaconductor`.
Run `uv sync --project D:/MediaConductor` yourself after pulling changes,
rather than letting a client launch do it.

## Verify the server command

Run the command outside the MCP client to confirm the catalog is available:

```powershell
uv --project D:/MediaConductor run --no-sync mediaconductor modes --mode manga-video --json
```

The MCP server communicates over standard input/output, so it normally waits
silently when started by hand. Long-running MCP operations should use the
typed `job_start` tool and then poll with `job_status`.

## Startup fails with "Access is denied"

A client reporting `calling "initialize": EOF`, with uv logging a build just
before it:

```
Building media-conductor @ file:///D:/MediaConductor
   Built media-conductor @ file:///D:/MediaConductor
error: failed to remove file
  `D:\MediaConductor\.venv\Lib\site-packages\../../Scripts/mediaconductor.exe`:
  Access is denied. (os error 5)
```

is not a permissions problem and not an MCP problem. `uv run` decided the
project needed reinstalling, and reinstalling rewrites the console scripts —
but Windows locks a running `.exe` against replacement, so any MediaConductor
server already running from that venv blocks the new one from starting. uv
aborts before the server ever speaks, and the client sees EOF.

Fix it in either order:

1. **Stop clients from syncing at launch** — add `--no-sync` to the `uv run`
   entry, or use the venv executable directly as above. A client launch should
   never mutate the environment it is launching from.
2. **Remove the reason uv wants to reinstall.** The usual cause is installed
   metadata that no longer matches `pyproject.toml` — an editable install still
   registered under an older version number makes *every* `uv run` rebuild.
   Compare them:

   ```powershell
   Select-String '^version' D:/MediaConductor/pyproject.toml
   Select-String '^Version' D:/MediaConductor/.venv/Lib/site-packages/media_conductor-*.dist-info/METADATA
   ```

   If they differ, close every MediaConductor server and repair the venv once:

   ```powershell
   uv sync --project D:/MediaConductor --reinstall-package media-conductor
   ```

Because a checkout install is editable, stale metadata does not mean stale
code — the running server is always the current source tree. Only the recorded
version number drifts, which is why the symptom is a failed launch rather than
wrong behaviour.

To find what holds the lock:

```powershell
Get-CimInstance Win32_Process -Filter "Name='mediaconductor.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine
```

Editors that manage MCP servers keep them alive between sessions, so the
blocking process is usually a server an editor started earlier, not a stray
shell.

## Server handshake

| Field | Value |
| --- | --- |
| `serverInfo.name` | `media-conductor` |
| `serverInfo.version` | the installed `mediaconductor` version |
| `protocolVersion` | `2025-11-25`, falling back to `2025-06-18` or `2024-11-05` |
| Capabilities | `tools` only — no resources, prompts, or sampling |
| Transport | stdio, newline-delimited JSON-RPC 2.0 (requests capped at 1,000,000 characters) |

`initialize` also returns server instructions covering the untrusted-page-text
rule, the vision-review requirement, and the recorded-review contract.

## Tool catalog

`tools/list` returns **49 tools**. Schemas come from
[`mediaconductor/command_spec.py`](mediaconductor/command_spec.py) — the same
table `mediaconductor commands --json --full` publishes — so the MCP schema and
the CLI can never drift. Every call shells out to the matching
`mediaconductor` subcommand.

Required arguments are listed below; every other argument is optional. `items`
accepts folder names and ranges, e.g. `["01", "05-08"]` — **omitting it selects
every item in the project**, which matters for the expensive generation tools.

### Install and environment (6)

| Tool | Required | Purpose |
| --- | --- | --- |
| `modes` | — | Show the manga-video catalog, dependencies, and MCP restart command. |
| `setup` | — | One-command provisioning: core binaries, AI tool envs, model downloads. Very long-running; safe to re-run; `dry_run` previews. |
| `doctor` | — | Check ffmpeg/uv/git, GPU backend, installed AI tools; `check_updates` also checks upstream. |
| `where` | — | Resolved paths (data root, tools home) and version. Run this first. |
| `workspace_layout` | — | Every resolved persistent root and whether it stays inside the workspace. `strict` exits non-zero on escape. |
| `install_tool` | `name` | Install one external AI env: `kokoro-82m`, `index-tts`, `magi-v3`, `deepseek-ocr2`. Multi-GB, long-running. |

### Acquire and crop (7)

| Tool | Required | Purpose |
| --- | --- | --- |
| `download` | — | Fetch MangaDex chapters politely and resumably; `all` takes the whole series. Long-running. |
| `style_detect` | `project_root` | Decide webtoon (→ `webtoon_split`) vs paged manga (→ `page_split`) from page dimensions, with samples to confirm by eye. |
| `webtoon_split` | `project_root` | Crop webtoon strips into panels and write verify sheets. Exit 3 = crops exist but are **not** approved. |
| `webtoon_cutcheck` | `project_root` | Full-resolution review windows around every forced cut and short panel. Open every listed window, not just the montage. |
| `webtoon_override` | `file`, `project_root` | Record merge/split fixes with indices resolved from the ranges manifest — never compute merge indices by hand. |
| `page_split` | `project_root` | Crop paged manga with MAGI v3 and write verify overlays. Long-running; MAGI boxes are proposals, not approvals. |
| `panels_remap` | `project_root` | After a re-split, map archived panels to new crops and carry narration + audio across. Dry run until `apply=true`. |

### Narration (4)

| Tool | Required | Purpose |
| --- | --- | --- |
| `panel_transcript` | `project_root` | Optional DeepSeek-OCR 2 pass into `transcript.json`, SHA-256-bound to each crop. An untrusted cross-check, never a substitute for reading pixels. Long-running. |
| `narration_edit` | `project_root`, `item` | Upsert/delete/list `narration.json` or `intro.json` entries; `prune_audio` drops the WAVs of changed lines. |
| `narration_check` | `project_root` | Structural validation: files parse, images exist, stems unique, no empty narration. |
| `narration_review_sheets` | `project_root` | Sheets pairing each panel with its narration line for the human pass. Exit 3 = artifacts ready, not approved. |

### Review, decisions, and rights records (3)

| Tool | Required | Purpose |
| --- | --- | --- |
| `manga_review` | `action`, `project_root` | Record or check the hash-bound reviews: `crop`, `narration`, `final-video`, `check`. |
| `panel_decisions` | `project_root` | Account for every crop — narrated, or deliberately omitted with a stated reason bound to its SHA-256. Without `panels`/`reason`/`reviewer` it audits instead. |
| `manga_rights` | `action`, `project_root` | `init` / `check` / `show` the rights manifest that authorizes publication. Fails closed. |

### Audio, render, and join (7)

| Tool | Required | Purpose |
| --- | --- | --- |
| `video_check` | `project_root` | Pre-flight: narration vs panels vs audio counts and name matches. |
| `audio_audit` | `project_root`, `audio_root` | ffprobe every expected narration WAV; `fix=true` deletes bad audio so the next run recreates exactly those. |
| `generate_audio` | `project_root`, `audio_root` | Kokoro TTS per panel. Long-running; old takes are archived, never lost. Blocked without current crop + narration records. |
| `render_videos` | `project_root`, `audio_root`, `output_root` | One video per item from panels + audio. Long-running. |
| `build_long_video` | `project_root`, `output_root` | Join item videos into one long video (no music — use `add_bgm`). Long-running. |
| `add_bgm` | `project_root`, `output_root`, `background_music` | Mix background music into the joined video without re-joining. `replace=true` overwrites in place. |
| `run_full_pipeline` | `project_root`, `audio_root`, `output_root` | Audio → fade → render → optional join/BGM/normalize → validate. Very long-running; prefer the single steps while iterating. |

### Validation and QA (4)

| Tool | Required | Purpose |
| --- | --- | --- |
| `video_validate` | `project_root` | Generated audio/videos vs inputs: stream formats, durations, counts. |
| `video_chapters` | `project_root`, `output_root` | Cumulative, paste-ready YouTube chapter timestamps probed from the item renders. |
| `video_quality` | `project_root`, `output_root` | Measure the encoded deliverable: loudness, true peak, drift, black/frozen frames, silence, stale renders, plus extracted review frames. Exit 3 = machine-clean with review outstanding. |
| `work_qa` | `project_root` | Aggregated machine-checkable gate over crops/narration/audio/renders, each problem carrying its exact fix command. |

### Project state and multi-agent coordination (8)

| Tool | Required | Purpose |
| --- | --- | --- |
| `library_list` | `project_root` | Projects and per-item readiness under a project root. Read-only. |
| `series_plan` | `project_root` | Slice items into fixed upload batches (12 by default) and name the next batch to produce. |
| `series_mark_published` | `project_root`, `items`, `video_id` | Record an uploaded batch in `publish.json` so `series_plan` advances. |
| `work_status` | `project_root` | Dashboard + resume command: per-item stage, active claims, recent notes. `next=true` returns only unclaimed actionable tasks. Run first in every session. |
| `work_claim` | `project_root` | Atomic TTL lease on an item+stage or a shared resource (e.g. `gpu`) so concurrent agents never duplicate work. |
| `work_note` | `project_root` | Append-only shared notebook for handoff (names, speakers, tone, warnings). Omit `add` to read. |
| `work_todo` | `project_root` | Shared session todo list for plan-level next steps the filesystem cannot derive. Survives a mid-project switch to another model. |
| `work_artifacts` | `project_root` | Inventory of reusable generated artifacts with a reuse hint each — check before regenerating anything expensive. |

### Thumbnail and publishing (7)

| Tool | Required | Purpose |
| --- | --- | --- |
| `thumbnail_compose` | `base`, `output` | Compose a 1280×720 thumbnail from an **approved source panel** plus stroked text blocks, block arrows, and an inset border. The base must be listed under `thumbnail_sources` in `rights.json`. |
| `youtube_profiles` | — | List isolated account profiles, connection state, and cached channel. Check before publishing. |
| `youtube_status` | — | Status for one profile; `verify=true` refreshes the token and queries the channel. |
| `youtube_upload` | `project_root`, `video`, `title` | Resumable upload through the selected profile. Long-running; default privacy is private; 1,600 quota units. |
| `youtube_list` | — | The profile's uploads and their ids (~2 quota units). |
| `youtube_delete` | one of `video_id` / `url` | Look up and irreversibly delete one video. Requires `confirm=true`; otherwise returns a preview. |
| `youtube_thumbnail` | `video_id`, `image` | Set or replace a thumbnail without re-uploading. Needs a verified account. |

### Background jobs (3)

| Tool | Required | Purpose |
| --- | --- | --- |
| `job_start` | `tool` | Run one long-running tool detached and return a job id. Arguments are validated against that tool's typed schema — raw argv is deliberately not accepted. |
| `job_status` | `job_id` | State (`running` / `succeeded` / `review_required` / `failed` / `orphaned`), exit code, progress markers, parsed result payload, log tail. |
| `job_list` | — | All background jobs with ids, commands, and states. |

`job_start` accepts exactly these targets:

```
build_long_video  download   generate_audio  install_tool  page_split
panel_transcript  render_videos  run_full_pipeline  setup
webtoon_split     youtube_upload
```

Anything else is rejected with *not marked long-running; call it directly*, and
`job_start` cannot invoke itself.

## Result shape

Every `tools/call` returns one JSON text block:

| Key | Meaning |
| --- | --- |
| `exit_code` | The subcommand's exit status. |
| `review_required` | True when the exit code is 3, or the JSON report says so. **Exit 3 is not success** — artifacts exist and a human review is outstanding. |
| `result` | Parsed `MEDIACONDUCTOR_RESULT` payload, when the command emits one. |
| `report` | Parsed JSON report for commands the server auto-appends `--json` to. |
| `output` | Raw stdout, for commands without a JSON report. |
| `stderr` | Trimmed stderr, when non-empty. |

`isError` is set only for exit codes other than 0 and 3. Oversized values are
head+tail clipped at 8,000 characters (2,000 for stderr) with an explicit
`truncated` marker, so nothing is silently dropped.

## Workspace confinement

Every filesystem-bearing argument is resolved and checked against the
`--allow-root` policy *before* argv is built — including arguments nested
inside `job_start`, and the configured defaults a command would otherwise pick
up silently (audio/output/work roots, background music, speaker WAV, the
configured project root). Path arguments that escape are rejected; they are
never clamped into the workspace.

Two further classes are validated by shape, not just location:

- Relative subpaths (`source_subdir`, and `panels_remap`'s archive run) must be
  portable relative paths with no traversal segments.
- Single-segment names (`download`'s `name`, `project_name`, `old_run`) must be
  one portable filename — reserved Windows device names included.

If `--allow-root` is omitted the server allows only its startup working
directory. This is a same-user stdio boundary: it reduces accidental
filesystem reach, and is not a sandbox against a hostile local process.

## Review gates

There is no confirmation argument to set. The audio, render, join, and
full-pipeline tools verify hash-bound review records themselves and refuse to
run without current ones; `youtube_upload` additionally requires a current
final-video record for the exact file plus a complete rights manifest.

Record approvals with the `manga_review` tool after the corresponding visual
pass:

```json
{"tool": "manga_review", "arguments": {
  "action": "crop", "project_root": "D:/MediaProjects/library/Recap",
  "items": ["01"], "reviewer": "sam"}}
```

Set them only after a vision-capable reviewer has opened every original
page/strip overlay, every actual crop, and every panel/narration pairing —
and, for `final-video`, after a complete normal-speed watch/listen pass of the
final export. MAGI-v3 confidence, DeepSeek-OCR2 output, or the existence of
review sheets does not satisfy that. Because each record is bound to the exact
bytes it covers, a later re-crop, rewrite, or re-encode invalidates it
automatically.

## CLI-only commands

The manga-video catalog has 68 CLI commands and 49 MCP tools. These 19
subcommands exist but are **not** reachable over MCP — run them in a terminal:

| Command | What it does |
| --- | --- |
| `bootstrap-tools` | Download ffmpeg/uv/git-lfs into this install's own tools dir (`setup` runs it when they are missing). |
| `smoke-test` | Build and verify a tiny real video to prove the install works end to end. Run after `setup`. |
| `commands` | List every command, or emit the full machine-readable catalog with `--json --full`. |
| `tools` | Show where the manga tool envs (Kokoro / IndexTTS / MAGI / DeepSeek OCR) resolve. |
| `mcp` | The MCP server entry point itself. |
| `youtube-auth` | Connect a named account profile through browser consent. |
| `youtube-logout` | Disconnect one profile by deleting only that profile's token. |
| `index-tts` | Run IndexTTS directly inside its external uv env. |
| `video-audio-indextts` | Generate per-item narration audio with IndexTTS instead of Kokoro. Long-running. |
| `video-fade-audio` | Apply fade in/out to item narration audio. |
| `video-normalize-audio` | Loudness-normalize the joined long-video audio. Long-running. |
| `video-clean-audio` | Clear generated audio for selected items — archived, not lost. |
| `video-clean-video` | Delete rendered item videos. |
| `video-clean-work` | Delete the `work/` scratch directory. |
| `video-clean-all` | Delete all generated output for a project in one go; source chapters are untouched. |
| `audio-takes-list` | List previously archived audio takes (`old/run_NNNN/`). |
| `audio-takes-restore` | Restore an archived take as the active audio instead of regenerating it. |
| `gutter-split` | Low-level gutter-splitting engine behind the crop commands. |
| `panels-context-pack` | Pack a chapter's panels into a labelled ZIP so an LLM can read them as narration context. |

`youtube_status` and `youtube_upload` open browser consent on demand, so
`youtube-auth` is only needed to connect a profile ahead of time. The cleanup
commands stay off MCP because they are destructive and require an allowed
generated root plus exact directory-name confirmation.

Discover their exact arguments with:

```powershell
uv --project D:/MediaConductor run mediaconductor commands --json --full
```
