# MediaConductor — guide for AI agents changing this codebase

MediaConductor is an agent-native CLI and MCP server for **manga, manhwa, and
webtoon recap videos**. Heavy AI tools live in isolated `uv` projects. **There
is no GUI.** The Python package and compatibility command remain
`mediaconductor` during the 2.x migration.

The product used to carry two more pipelines — AI story videos and generated
song/lyrics videos — plus generic image export. They were removed: each brought
its own multi-gigabyte toolchain, its own manifest format, and its own review
semantics, and the shared surface (one CLI table, one MCP catalog, one setup
plan) made every one of those a place for the manga path's guarantees to leak.
One product, one review model.

This file is for **changing MediaConductor itself**. For *using* it, begin with
[docs/ai-guide.md](docs/ai-guide.md) and load
[skills/manga-video/SKILL.md](skills/manga-video/SKILL.md).

## Which doc for which job

| Job | Doc |
|---|---|
| CLI/MCP contract for agents | [docs/ai-guide.md](docs/ai-guide.md) |
| Quality design: what is automated, what needs eyes and ears | [docs/manga-quality-design.md](docs/manga-quality-design.md) |
| Fresh clone/machine setup + verification | [docs/setup.md](docs/setup.md) |
| Produce a recap series (URL → uploads) | [.claude/skills/manga-recap/SKILL.md](.claude/skills/manga-recap/SKILL.md) |
| Manga CLI/MCP reference | [docs/manga-video-guide.md](docs/manga-video-guide.md) |
| Crop → verify → narrate loop details | [docs/operate/crop-verify-narrate.md](docs/operate/crop-verify-narrate.md) |
| Full production recipe + troubleshooting | [docs/recap-video-playbook.md](docs/recap-video-playbook.md) |
| Several agents on one project / resuming / switching LLM mid-project | [docs/multi-agent.md](docs/multi-agent.md) |
| External AI tool envs, installs, YouTube, releases | [docs/external-tools.md](docs/external-tools.md), [docs/install-tools.md](docs/install-tools.md), [docs/youtube.md](docs/youtube.md), [docs/publishing.md](docs/publishing.md) |
| Why a guard/invariant exists (incident stories) | [docs/history/incidents.md](docs/history/incidents.md) |

## Code map — `mediaconductor/`

Each package has its own README.md with entry points and gotchas.

| Stage | Package / module | What it does |
|---|---|---|
| core | `cli.py`, `command_spec.py`, `runtime.py`, `config.py`, `paths.py`, `library_scan.py`, `series_plan.py`, `mcp_server.py`, `jobs.py`, `workboard.py`, `qa_loop.py`, `workspace.py` | dispatch, shared command schemas, self-spawning, config, batch planning, MCP server, background jobs, multi-agent board, resolved-root reporting |
| gates | `reviews.py`, `panel_decisions.py`, `rights.py` | hash-bound crop/narration/final-video approvals, per-panel omission decisions, the fail-closed rights manifest |
| acquire | `download/` | MangaDex fetch (polite, resumable, writes `manga.json`) |
| acquire | `panels/` | crop: `webtoon-split`, `page-split` (MAGI), cutcheck, overrides, remap |
| read | `ocr/` | DeepSeek-OCR 2 panel transcripts |
| produce | `video_pipeline/` | narration contract, editorial timeline, audio → faded derivatives → render → join → BGM → final normalize → encoded-output quality gate |
| produce | `audio/` | IndexTTS pipeline, narration safety/quality lints, TTS provenance |
| publish | `youtube/` | OAuth, resumable upload, list/delete/thumbnail |
| tools | `tools/` | isolated external AI tool envs + vendored ffmpeg/uv/git-lfs |
| shared | `images/`, `utils/` | thumbnail compose, panel context packs, archive/result helpers |

## Architecture (what calls what)

- **One CLI.** Everything dispatches from the `COMMANDS` dict in
  `mediaconductor/cli.py` (`name -> (module, function, group, help)`); modules are
  imported **lazily** so `--help` never pulls in torch/opencv. To add a
  command: write a module with a `main()` doing its own argparse, add one
  line to `COMMANDS`. Pipeline code shells out to other subcommands via
  `mediaconductor.runtime.cli_command(...)` (works frozen and unfrozen).
- **One schema table.** `mediaconductor/command_spec.py` declares each
  agent-facing command's arguments once; the MCP server serves them as tool
  schemas and `commands --json --full` publishes them to shell agents. **If
  you add/change a subcommand flag, update command_spec.py in the same
  change** — it is what agents see.
- **MCP server** (`mediaconductor/mcp_server.py`): stdlib-only JSON-RPC over
  stdio; every tool shells out to the CLI. The catalog is the manga catalog —
  no router mode, no `--all-tools`; a tool outside the mode answers *unknown*,
  not "forbidden", so a removed feature cannot be probed by name. Long-running
  work must go through the `job_start`/`job_status` tools, never a blocking
  call. Public startup always applies `--allow-root` (the current directory by
  default) to direct, nested-job, and configured-default filesystem paths,
  including review records, rights manifests, and final-video paths.
- **Background jobs** (`mediaconductor/jobs.py`): `job-start --tool NAME
  --arguments-json OBJECT` only. Raw positional argv is rejected — it was a
  strictly *wider* interface than the MCP call it mirrored, so anything the
  schema refused could be smuggled through as a bare flag, including reaching a
  lower-level render command to skip a review gate. The supervisor logs to
  `<work>/jobs/<id>.log` and records exit code + `MEDIACONDUCTOR_RESULT` into
  `<id>.json`; `job-status` / `jobs` read it back, detecting orphaned
  (dead-supervisor) jobs.
- **The item pipeline** (`video-*`): `video` = audio (`video-audio` Kokoro /
  `video-audio-indextts`; `--tts auto` prefers IndexTTS when GPU + model +
  speaker WAV exist) → symmetric 8 ms per-clip fade derivatives →
  `video-render` (frame-aligned to faded audio) → optional `video-join` →
  `video-add-bgm` → one final two-pass `video-normalize-audio` (−14 LUFS,
  −1.5 dBTP). Production defaults to `audio_faded/<project>/...`; raw TTS
  under `audio/` is never modified and `--audio-source raw` is an explicit
  diagnostic override. Any BGM change invalidates final normalization, so a
  standalone re-mix must be normalized again after the music is mixed.
- **The review gates** (`mediaconductor/reviews.py`): crop, narration, and
  final-video approvals are stored in `<project>/.mediaconductor/manga-reviews.json`
  beside SHA-256 snapshots of the exact inputs, so any change to a source page,
  panel, narration file, or the output MP4 invalidates the record without
  anyone having to notice. `enforce_production_reviews()` runs in `video`,
  `video-audio`, `video-audio-indextts`, `video-render`, and `video-join`, so a
  direct subcommand call and a background job hit the same gate as the
  pipeline. **There is no bypass** — the old `--review-policy warn` was removed
  because an escape hatch is exactly what a run under time pressure reaches for,
  and an unreviewed render is indistinguishable from a reviewed one once it
  exists.
- **External AI tools** (Kokoro, IndexTTS, MAGI, DeepSeek-OCR 2) live in
  isolated uv envs under `<install>/.mangaeasy/tools/<tool>/`
  (`install-tool`, resolved by `tools/external.resolve_tool_dir()`).
  `tool_env()` **force-pins** HF/torch/uv caches under `<data>/.mangaeasy/`
  (opt-out: `MEDIACONDUCTOR_SHARE_CACHES=1`). `ensure_vendored_path()` at the top
  of cli.py makes bare `"ffmpeg"`-style calls resolve to vendored binaries.

## Data layout

Everything persistent lives below one workspace so a production can be moved,
backed up, or deleted as a unit. `mediaconductor workspace-layout --json`
reports every resolved root and whether it escaped; `doctor` warns when one has.

```
library/<project>/            source items; manga.json (machine-managed source record)
  01/panels/ 01/narration.json [01/intro.json] [01/transcript.json]
  01/panel_decisions.json     why each un-narrated panel is omitted (hash-bound)
  rights.json                 source, permission basis, consent, safety scans
  .mediaconductor/manga-reviews.json   hash-bound crop/narration/final-video approvals
audio/<project>/<item>/*.wav  per-panel narration; each with a *.wav.json provenance sidecar
audio_faded/<project>/<item>/*.wav  production render derivatives; raw TTS untouched
output/<project>/             item videos + <project>_full.mp4 + quality/ reports
work/                         scratch incl. jobs/ — video-clean-work clears it
bgm/ vocal/                   user-owned licensed music and narrator references
.mediaconductor/              tools/, cache/, state/, gitignored OAuth secrets
```

Roots default from env (`MEDIACONDUCTOR_ITEMS_ROOT`/`MEDIACONDUCTOR_AUDIO_ROOT`/
`MEDIACONDUCTOR_OUTPUT_ROOT`/`MEDIACONDUCTOR_WORK_DIR`; bare legacy names still
honoured) but agents pass explicit `--project-root library/<P>` etc.
Config: `config.json` (per-project) + `config.system.json` (machine defaults)
via `mediaconductor/config.py` — its loaders raise `ConfigError` (the CLI
dispatcher renders it; never `sys.exit` from library code). Note
`config.PROJECT_ROOT` is the *workspace* root, not the `--project-root` flag.

## Invariants (each earned by a shipped failure — stories in [docs/history/incidents.md](docs/history/incidents.md))

- **Archive, never overwrite, generated output**: use
  `archive_before_overwrite()` / `archive_into_run()` from `mediaconductor/utils`
  (`old/run_NNNN/`). `audio-takes-list/-restore` browse the archives.
  `video-clean-*` are the only sanctioned deleters and never touch `library/`.
- **`load_narration()` (`video_pipeline/item_assets.py`) is the only
  narration reader** — it alone knows `intro.json` prepending, and it validates
  every entry through `video_pipeline/narration_contract.py` so no consumer
  re-derives what a safe `image` value is. The contract is strict on purpose:
  basenames only (no path separators, traversal, drive or UNC paths), resolved
  containment inside `panels/`, case-insensitive filename *and stem*
  uniqueness (audio is `<stem>.wav`), no unknown properties, bounded motion and
  pause values. `workboard._narration_entries()` is the one deliberately
  tolerant reader — the board answers "which stage is this item in", so a file
  that needs one fix must still read as narrated.
- **Every generated WAV carries a provenance sidecar** (`audio/provenance.py`):
  normalized narration digest, beat/panel identity, engine, model, voice,
  speaker-WAV digest, language, speed. A take is reused only when all of them
  match the current contract; otherwise it is archived and regenerated. "Skip
  if the file exists" silently shipped last week's sentence in last week's
  voice, and nothing but watching the whole video could catch it.
- **Every cropped panel is accounted for**: narrated, or carrying a hash-bound
  omission decision from a fixed reason vocabulary (`panel_decisions.py`). The
  previous "confirm none is a story panel" warning recorded nothing, so a
  dropped story panel and a skipped credits page looked identical.
- **Production manga renders use faded derivatives, not raw clip edges**:
  `audio_faded/` contains symmetric 8 ms fade-in/fade-out copies and `audio/`
  remains the recoverable TTS source. Keep `--audio-source raw` opt-in.
- **Adaptive tail declick in `video-fade-audio`**: IndexTTS occasionally leaves
  a spurious click/pop burst a few ms before a clip's true end — real speech
  decays to near-silence, then a short loud burst appears with no further
  decay before the file just stops. A fixed 8 ms fade-out lands mid-artifact
  and only partially attenuates it (still audible). `compute_adaptive_fade_out_ms()`
  in `preprocess_audio_fades.py` detects that quiet-then-burst tail shape (a
  trailing loud run preceded by ≥20 ms of real silence) and extends the
  fade-out to start before the burst; ordinary clips are untouched. This is a
  generation-random artifact, not reliably tied to narration wording — don't
  try to "write around" it in narration text; the pipeline is the fix. `--no-declick`
  opts out for diagnostics only.
- **Mix BGM before one final whole-mix normalize** to −14 LUFS / −1.5 dBTP.
  Never normalize narration, add music, and call the result final; every BGM
  change requires another final two-pass normalization pass. Keep the
  normalizer's AAC peak margin: codec reconstruction can overshoot the
  pre-encode true-peak target.
- **Narration gain has exactly one owner**: a BGM-bound full pipeline joins at
  unity and applies the configured lift during mixing; narration-only joins
  apply it themselves. Standalone BGM remixing defaults to unity because its
  joined input already contains the configured voice gain.
- **`amix=…:normalize=0` and `alimiter=level=disabled`** in
  `build_mix_filter()` — each silently undid the −14 LUFS target once;
  test-guarded in `test_music_bed.py`.
- **dB-native volume flags only** (`--music-volume-db`, default −30 — a true
  LU separation now that the bed is loudness-aligned to the measured
  narration first; −30 keeps the bed comfortable over a long watch instead of
  fatiguing the listener (was −26, then −28, both still read as too present
  per viewer feedback; keep new defaults within −20…−32). Never a linear
  multiplier.
- **`cudnn.benchmark` stays False** in `kokoro_batch_worker.py`;
  `--gpu-workers` is clamped to 4 by `clamp_gpu_workers()`.
- **Resume-pruning is shard-aware** (`prune_recent_audio_for_resume(...,
  shards=...)`) — keep it so if you touch sharding.
- **Freshness-gated renders** (`stale_reason()`): don't restore
  skip-if-exists. `video-join` is strict about missing items; `--allow-gaps`
  is only for genuine source gaps.
- **Item selection compares `item_value()`** (handles "2.1"), not
  `item_number()`.
- **Workboard state (`notes.jsonl`, `todo.jsonl`) is append-only, never
  read-modify-write**: each mutation is one small `O_APPEND` write, so two
  agents (or two different LLMs, mid-handoff) writing at once can't tear a
  record; current state is a fold over the log, not a stored snapshot. Don't
  "simplify" `work-todo`/`work-note` into rewriting the file in place — that
  reintroduces the race the log format exists to avoid.
- **UTF-8 stdio forcing in cli.py stays** (Windows pipes are cp1252).
- **Machine contract stays stable**: exit 0/1/2/3 (3 = artifact created but review required); `--json` commands print
  exactly one JSON object on stdout; generation commands end with
  `MEDIACONDUCTOR_RESULT {...}` (`utils.emit_result()`); `MEDIACONDUCTOR_PROGRESS n/m`
  ticks. Pipeline commands never prompt on stdin. Live YouTube operations may
  open the explicit OAuth browser flow unless `--no-auto-auth` is set; browser
  progress must remain on stderr so JSON stdout stays parseable.
- **YouTube**: tokens are secrets (print paths/booleans, never contents);
  default privacy stays `private`; scopes stay video-management-only; the
  upload is hand-rolled resumable `requests` — don't add the discovery client.
  Replacement defaults to upload-new → verify → delete-old. Deletion-first is
  irreversible and permitted only when the user explicitly requests it; first
  verify the exact profile, channel, and old video id, then delete with
  `--confirm`, upload the replacement, replace the publish record, and verify
  the new listing.
- **MangaDex politeness is a feature** — keep the complete-chapter fast-skip
  and the rate spacing; never parallelize downloads.
- **Batches don't shift**: `series-plan` windows are fixed over the sorted
  item list even when items are added.

## Tests, lint, CI

- `uv run pytest` (pure-logic suite + docs cross-reference checks; add a test
  when fixing a logic bug) and `uv run ruff check .` must pass before commit.
  CI runs both plus compileall on all three OSes; release additionally
  smoke-tests the frozen CLI.
- `mediaconductor smoke-test` renders a tiny real video — the proof an env works.
- Packaging: `packaging/mediaconductor.spec` (PyInstaller); `scripts/release.py`
  keeps the version fields in lockstep. Data-root resolution for installed
  apps lives in `_default_frozen_root()` — never assume `~/.mangaeasy`.

## Conventions

- Lazy imports for anything heavy; import inside the subcommand's module.
- Every pipeline stage works CPU-only; GPU is an optimization (`--device
  auto|cuda|cpu`, encoder fallback to libx264).
- Long steps: launch in the background (harness background shell or
  `mediaconductor job-start`) and wait for completion; GPU tools block-buffer
  stdout, so judge liveness from filesystem signals or `job-status`, not log
  tails.
- Agents edit data through commands (`narration-edit`, `webtoon-override`),
  not by hand-editing JSON; keep new agent-facing state editable through a
  command.
- Git commits only when the user explicitly asks — don't commit proactively
  after a fix, even if tests pass.
