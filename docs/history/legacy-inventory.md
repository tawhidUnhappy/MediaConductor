# Legacy vs. new inventory + removal blast radius

Companion to `reorg-plan.md`. This is the per-module classification the Phase 2
removal works from, and the **desktop dependency map** that gates it.

## Command classification

### KEEP — the item pipeline (recommended workflow) and shared infra

`video`, `video-audio`, `video-audio-indextts`, `video-render`, `video-join`,
`video-add-bgm`, `video-check`, `video-validate`, `video-audio-audit`,
`video-fade-audio`, `video-normalize-audio`, `video-clean-*`,
`audio-takes-list/restore`, `webtoon-split`, `gutter-split`, `download`,
`ai-zip`, all `youtube-*`, all `tools`/`index-tts`/`deepseek-ocr2`/`zimage`,
`to-pdf*`/`convert-images`/`watermark`, and core (`app`, `commands`, `where`,
`library-list`, `mcp`, `doctor`, `install-tool`, `bootstrap-tools`,
`ensure-node`).

### ADD — flagship (Phase 1)

`page-split` — real MAGI page-crop command with built-in verification sheets,
mirroring `webtoon-split`. Retires the scratch scripts in
`docs/recap-video-playbook.md` Phases 2–3.

### REMOVE — legacy chapter era

| Command | Module | Notes |
|---|---|---|
| `render-video` | `mangaeasy/video/render.py` | superseded by `video-render` |
| `add-bgm` | `mangaeasy/video/add_bg.py` | superseded by `video-add-bgm` |
| `join-chapters` | `mangaeasy/video/join.py` | superseded by `video-join` |
| `join-chapters-nobgm` | `mangaeasy/video/join.py` (`main_nobgm`) | same |
| `timestamps` | `mangaeasy/video/timestamps.py` | item pipeline computes these differently |
| `fade-audio` | `mangaeasy/audio/fade.py` | superseded by `video-fade-audio` |
| `normalize-chapter-audio` | `mangaeasy/audio/normalize_chapter.py` | superseded by `video-normalize-audio` |
| `process-panels` | `mangaeasy/panels/process.py` | MAGI-v2 upscale/mirror/bubble-clean; not in item flow |
| `cut-page` | `mangaeasy/web/cut_page.py` | Flask page-crop editor (human UI) |
| `panel-editor` | `mangaeasy/web/panel_editor.py` | Flask panel-arrange editor (human UI) |
| `narration-editor` | `mangaeasy/web/narration_editor.py` | Flask narration writer (human UI) |
| `narration-editor-all` | `mangaeasy/web/narration_editor_all.py` | Flask narration writer, all chapters |
| `narration-review` | `mangaeasy/web/narration_review.py` | Flask narration QA (human UI) |
| `join-narration` | `mangaeasy/narration/join.py` | chapter-layout narration helper |
| `normalize-narration` | `mangaeasy/narration/normalize.py` | " |
| `clean-narration` | `mangaeasy/narration/clean.py` | provides `clean_text_for_tts` (only legacy `audio/tts.py` uses it) |
| `backup-narration` | `mangaeasy/narration/backup.py` | " |
| `rename-file` | `mangaeasy/narration/rename_file.py` | " |
| `init-chapter` | `mangaeasy/utils/init_chapter.py` | single-chapter `config.json` bookkeeping |
| `increment-chapter` | `mangaeasy/utils/increment.py` | " |
| `reset-chapter` | `mangaeasy/utils/reset.py` | " |
| `fix-name` | `mangaeasy/utils/fix_name.py` | " |
| `clean-chapter` | `mangaeasy/utils/clean_chapter.py` | " |

Also fully removable as a package: `mangaeasy/narration/` (its
`load_narration`/`save_narration`/`clean_text_for_tts` are used **only** by the
legacy `audio/tts.py` and `web/narration_editor.py`) and `mangaeasy/audio/`,
`mangaeasy/video/`.

## Python coupling (verified 2026-07-09)

- **Nothing in the kept item pipeline imports any legacy module.** Grep for
  imports of `mangaeasy.video.` / `mangaeasy.audio.` / `mangaeasy.narration` /
  `panels.process` / the legacy web editors, excluding the legacy dirs
  themselves and `video_pipeline/`, returns **only `cli.py`'s `COMMANDS`
  entries**.
- **Two `load_narration`s exist** and must not be confused:
  - `mangaeasy/narration/__init__.load_narration` — legacy; consumed by
    `audio/tts.py` + `web/narration_editor.py` (both removed).
  - `mangaeasy/video_pipeline/item_assets.load_narration` — the item
    pipeline's single source of truth (**keep**; it's what handles
    `intro.json`).
- **No test references any legacy command.** `tests/test_cli_contract.py` and
  `tests/test_docs_crossref.py` iterate over *all* `COMMANDS`, so they update
  automatically when the legacy entries are deleted from the dict.

Conclusion: the **Python** removal is mechanical and low-risk.

## ⚠ Desktop dependency map — the real blast radius (gates Phase 2)

The removal is *not* purely internal. The Electron **renderer** wires several
legacy commands into user-facing tabs (the desktop **main** process is generic
— it just spawns whatever command string the renderer sends, so the coupling is
entirely in the renderer):

| Desktop surface | File | Legacy commands it uses |
|---|---|---|
| **Workflow** tab (single-chapter pipeline) | `desktop/src/renderer/src/views/Workflow.tsx` | `render-video`, `fade-audio`, `add-bgm`, `normalize-chapter-audio`; launches `cut-page`, `panel-editor`, `narration-editor` |
| **Editor** tab (embedded Flask editors) | `views/Editor.tsx`, `editor-context.tsx` | `cut-page`, `panel-editor`, `narration-editor`, `narration-editor-all`, `narration-review` |
| **Batch** tab (multi-chapter) | `views/Batch.tsx` | item pipeline only (`video-*`) — unaffected |

So "hard-remove legacy" also means **removing or rewriting the Workflow and
Editor tabs** — including the browser-based crop / panel / narration-writing
editors, which are the *human* path for exactly the crop→see→narrate loop this
project centers on.

**Open decision for the Phase 1 boundary report** (recommended option first):

- **A. Migrate then remove.** Rebuild single-chapter Workflow on the item
  pipeline (or fold into Batch) and replace the Flask editors with an
  item-pipeline equivalent, *then* delete legacy. Safe, preserves the human
  UI, larger effort.
- **B. Remove tabs too.** Delete the Workflow + Editor tabs, keep only Batch.
  Smallest code, but drops the single-chapter UI and the human crop/narration
  editors — arguably contradicts "let humans work on it too."
- **C. Keep the human editors, remove the rest.** Treat `cut-page` /
  `panel-editor` / `narration-editor*` as *kept UI* (they serve the flagship
  loop) and remove only the superseded render/audio chapter commands after
  migrating Workflow's render chain to the item pipeline.
