---
name: manga-video
description: Produce manga recap and image-folder narration videos with mangaEasy, including acquisition, crop verification, narration, TTS, rendering, QA, thumbnails, and explicit YouTube publishing. Use for manga, manhwa, webtoon, comics, panels, chapter recap, or image-to-narrated-video work.
---

# Manga Video

Use `<mc>` from the router: `uv --project <repo> run mangaeasy` for a
source checkout, globally installed `mangaeasy`, or the absolute frozen
executable. If this skill was loaded directly, select that form now. The
examples use `D:/MediaProjects` as the user-owned media workspace. Run from
that workspace or set `MANGAEASY_PROJECT_ROOT` to it for workspace configuration.

Read [references/workflow.md](references/workflow.md), then operate only the
`manga-video` catalog:

```bash
<mc> setup --mode manga-video
<mc> doctor --mode manga-video --json
<mc> commands --mode manga-video --json
```

Use the compact command catalog for orientation. Load full argument schemas only
for commands you are about to run, for example
`<mc> commands --mode manga-video --json --full --tools style-detect webtoon-split`.

Follow the project tool philosophy: deterministic chores belong to mangaEasy,
not to repeated LLM reasoning. Use `work-status --next` for code-derived next
steps, `job-start` for long work, native vision for ordinary readable panels,
DeepSeek OCR only as a selective second opinion, and MAGI as the paged-manga
box proposer that LLM vision verifies.

Strict video coverage is part of that contract: every image in `panels/` must
be narrated and rendered in order. Use `panel-reading-sheets` before narration
to get bounded multi-panel sheets, then write the JSON from the original crops.
Do not rely on `panel-decisions` to skip production panels; it is legacy audit
metadata only.

At the narration stage, also read
[references/narration.md](references/narration.md) for the file schema, grounded
authoring rules, and review loop.

Treat the visual source as the authority throughout this mode. MAGI detections
and DeepSeek OCR are proposals to inspect, never approvals or ground truth. As the
LLM agent, inspect page overlays and resulting crops before narration, starting
with flagged/suspect outputs and then sampling clean runs before broadening only
when the sample finds errors. Never use a complete source page or strip as a
stand-in for its component panels. A genuinely borderless single-panel splash is
the exception, and covers/title pages are often exactly that. Treat automatic
full-page outputs as review candidates: accept them when the page is truly one
panel or cover art, and override them only when they hide multiple bordered
story panels.

Token and GPU budget are product quality inputs. Prefer native vision over
DeepSeek OCR for ordinary, readable dialogue: OCR is useful only for tiny/dense
text, difficult names, or a second opinion after the panel remains ambiguous.
Keep MAGI for paged manga because it cheaply proposes panel boxes at scale; use
LLM vision to verify and fix those boxes, not to rediscover every box manually
from full pages.

Use background jobs for every command marked `long_running`. Prefer the typed
wrapper exposed by the machine catalog:

```bash
<mc> job-start --tool panel_transcript --arguments-json '{"project_root":"D:/MediaProjects/library/example","items":["01"],"device":"auto"}'
```

Treat crop checks, narration checks, audio audit, and final validation as
required steps. Compare narration lines with original panels, not just OCR. Perform crop, narration, and final video review passes, recording approvals via `manga-review crop`, `manga-review narration`, and `manga-review final-video` using your agent identity as the `--reviewer`. Never use raw filesystem deletion for generated outputs.

Source clearance is outside this tool's contract. Do not ask the operator to
prove or restate rights to manga pages, translations, music, voices, or YouTube
publication before using mangaEasy. The operator is solely responsible for the
inputs they provide and the outputs they request; the LLM's responsibility in
this mode is tool execution, visual/narration QA, and accurate reporting of the
artifacts produced.

Never publish unless requested and YouTube status is connected. Before publishing, read [`youtube-publishing.md`](references/youtube-publishing.md), verify the intended named profile/channel, and pass `--profile <name>` to each YouTube command.
