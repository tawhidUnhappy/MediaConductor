# Changelog

## Unreleased

### Removed

- **The rights system is gone** — `manga-rights`, `rights.py`, `rights.json`,
  and the `--rights-confirmed` / `--voice-consent-confirmed` /
  `--source-permission-confirmed` flags on `manga-review final-video`.
  Publication no longer asks the tool whether the source material is cleared
  for use; that is the operator's responsibility and is deliberately not
  modelled here. Removed at the owner's direction.

  What this removes with it, stated plainly so it is not discovered later: the
  recorded permission basis and its evidence, the voice-consent record, the
  music-licence and thumbnail-source lists, and the four platform-safety
  attestations (nudity, sexualized minors, graphic gore, misleading
  thumbnail). Nothing in the pipeline now records or checks any of them.

  **The final-video review gate is unchanged.** `youtube-upload` still refuses
  any file that is not covered by a current hash-bound `manga-review
  final-video` record, which still requires current crop and narration
  reviews. That gate answers "is this the file that was checked?" — it never
  answered "may this be published at all".

  Existing `rights.json` files are left on disk and simply ignored. Review
  records written earlier carry an `acknowledgements` block; it is ignored on
  read rather than rejected, so an in-flight project does not land back behind
  the gate on upgrade.

**The product is `mangaEasy` again, and every text-drawing command now renders
the same on Linux, Windows and macOS.** The rename is breaking; the portability
fixes are not.

### Changed

- **The Python package is now `mangaeasy`** (was `mediaconductor`). Entry
  points, env vars, and stdout markers follow, and each keeps a working
  compatibility path:
  - The command is `mangaeasy`; `mediaconductor` remains installed as an alias.
  - Env vars are `MANGAEASY_*`; `MEDIACONDUCTOR_*` values are mirrored at
    startup and keep working, so no install silently relocates a model cache.
  - Machine markers are `MANGAEASY_RESULT` / `MANGAEASY_PROGRESS`; scanners
    still accept `MEDIACONDUCTOR_*` (tool scripts already copied into external
    envs print them).
  - Review records move to `<project>/.mangaeasy/manga-reviews.json`. Reads fall
    back to `.mediaconductor/` and the next recorded review writes the merged
    store forward — approvals are hash-bound production gates, so a project
    reviewed under the old name must not land back behind them.
  - The MCP server name and PyPI distribution are `mangaeasy`; the PyInstaller
    spec is `packaging/mangaeasy.spec` and builds `mangaEasy` / `mangaEasy.app`.

### Added

- **A fully-isolated, zero-prerequisite install.** `bootstrap.sh` /
  `bootstrap.ps1` need only bash+curl+tar or PowerShell 5 — not even uv. They
  download a SHA-256-verified portable uv, a private Python, the dependencies
  and portable ffmpeg/git-lfs, all inside the install folder. Nothing is written
  to `~/.cache`, `~/.local`, `%LOCALAPPDATA%` or `/usr`, and no `PATH` entry or
  shell profile is touched: delete the folder and the machine is as it was. See
  [docs/portable-setup.md](docs/portable-setup.md), which also carries the
  per-OS download links, an offline procedure and an agent-followable checklist.
- `mangaeasy env` prints that environment for a shell (`--sh`/`--bat`/`--ps1`/
  `--json`) so `uv` run by hand inherits it, and `--check` exits non-zero when
  anything resolves outside the install folder. `where --json` and `doctor` now
  report isolation too.
- `mangaeasy tool-downloads` publishes the portable ffmpeg/uv/git-lfs URLs and
  digests per OS/arch, generated from the same table the downloader verifies
  against — so a machine with no outbound GitHub access, or an agent doing the
  fetching, cannot be given a stale link.

### Changed

- **Caches are pinned inside the install folder, and now that actually covers
  `uv sync`.** `tool_env()` already redirected HF/torch/uv caches for external
  tool subprocesses, but the main process was unpinned and — the real leak —
  `uv sync` runs *before any of our Python does*. It is what downloads the
  interpreter and every wheel, so a fresh setup still wrote ~270 MB to
  `~/.cache/uv` and `~/.local/share/uv/python`. `mangaeasy/isolation.py` is now
  the single definition; it is applied at CLI startup and exported in shell by
  `scripts/isolate.sh` / `scripts/isolate.cmd` before uv is invoked.
  `tests/test_isolation.py` asserts the two halves agree, because a silent drift
  here is invisible until a home directory fills up. `MANGAEASY_SHARE_CACHES=1`
  still opts out.
- **Core binaries are portable-first.** `ensure_core_tools()` downloads
  ffmpeg/uv/git-lfs into `runtime/tools/_vendor/` instead of accepting a copy
  already on `PATH`. A system binary breaks the "delete the folder" promise and
  makes renders depend on whichever encoders that particular build carries.
  `bootstrap-tools --system-ok` restores the old behaviour for constrained or
  offline machines.

### Fixed

- **Renders died instead of falling back when a hardware encoder was present but
  unusable.** `ffmpeg -encoders` lists what the binary was *compiled with*, not
  what it can *open*, and encoder selection trusted the list. The vendored
  FFmpeg is a rolling `master` build, so it can require a newer NVENC API than
  the installed driver offers ("Required: 13.1 Found: 13.0"); selection picked
  `h264_nvenc` and every segment failed on a machine whose libx264 path was
  fine. `encoder_works()` now probes each candidate with a one-frame encode
  (cached per process) and says why it skipped one, so "it used the CPU" is
  distinguishable from "there is no GPU". An explicitly requested encoder is
  still never substituted.
- **Long filter graphs broke on current ffmpeg.** FFmpeg 8 *removed*
  `-filter_complex_script` in favour of the generic `-/filter_complex`, so
  building the joined narration WAV aborted with "Unrecognized option" before
  doing any work. `filter_script_args()` picks the spelling this ffmpeg accepts;
  both must keep working, since the vendored build is rolling master while a
  distro or Homebrew ffmpeg may be 6.x or 7.x. Passing the graph as a file is
  not optional — inline, a 160-panel chapter exceeds Windows' 32,767-char argv
  limit.
- **Text drawn onto images was unreadable on Linux and macOS.** Six modules
  loaded fonts by bare name (`arialbd.ttf`, `impact.ttf`) or from hardcoded
  Debian/Windows paths. Pillow resolves a bare name only through the host font
  search — in practice Windows — so off-Windows every one of them fell through
  to `ImageFont.load_default()`, a face that ignores its size argument: a 48 px
  panel-index overlay rendered about 41x8 px. Nothing crashed, so it never
  surfaced as an error; the crop-review contact sheets and cutcheck strips the
  production gates depend on simply could not be read, and thumbnails composed
  at 104 pt came out with hairline text. `mangaeasy/fonts.py` is now the one
  resolver: it searches the real per-OS font directories (including the
  distro-specific layouts under `/usr/share/fonts`), then the TTF bundled in
  `assets/fonts/`, and only then Pillow's default *at the requested size*. A
  test asserts rendered width per call site, because the type alone no longer
  distinguishes a real face from the fallback.
- **`workspace-reset` and the `video-clean-*` commands could half-erase a tree
  on Windows.** `shutil.rmtree` cannot delete a read-only file there — the
  attribute is on the file, not the directory — so a delete aborted partway with
  a `PermissionError` traceback, which is the state those commands exist to
  avoid. They now use `utils.remove_tree()`, which clears the attribute and
  retries; on Linux and macOS the handler is never reached.
- `.bat` launchers are pinned to CRLF in `.gitattributes`. `* text=auto` was
  normalising them to LF, which cmd.exe mis-parses in multi-line blocks.
- `run.sh` now falls back to uv's known install locations (`~/.local/bin`,
  `~/.cargo/bin`, Homebrew) when it is not yet on `PATH` — the same fallback
  `run.bat` already had, and the common case right after installing uv or when
  launching from a GUI shell. Added `run.command` so macOS Finder can launch the
  bootstrap by double-click.

## 3.0.0 — 2026-07-26

**mangaEasy is now a manga recap product only, and review is a record
rather than an assertion.** Both changes are breaking.

### Removed

- Removed the AI Story and Song/Lyrics pipelines entirely: `story-*` and
  `song-*` commands, their MCP tools, manifests, skills, docs, and tests, plus
  the ACE-Step, Demucs, WhisperX, and Z-Image tool environments, installers,
  setup plans, and adapters. Each brought its own multi-gigabyte toolchain, its
  own manifest format, and its own review semantics onto one shared CLI table,
  MCP catalog, and setup plan — which is where the manga path's guarantees kept
  leaking. One product, one review model.
- Removed the MCP router mode and the `--all-tools` escape hatch. The manga
  catalog is the catalog, and a tool outside it now answers *unknown* rather
  than "forbidden", so a removed feature cannot be probed by name.
- Removed `manual_review_confirmed` and `final_video_review_confirmed`. A
  boolean a caller sets is not evidence that anyone looked at anything; see
  Added below for what replaced them.
- Removed `--review-policy warn`. There is no bypass anywhere — an escape hatch
  is exactly what a run under time pressure reaches for, and an unreviewed
  render is indistinguishable from a reviewed one once it exists.
- Removed raw positional `job-start <command> [args…]`. It was a strictly wider
  interface than the MCP call it mirrored: anything the schema rejected could be
  smuggled through as a bare flag, including reaching a lower-level render
  command to skip a gate. Only `--tool NAME --arguments-json OBJECT` remains.
- Removed the raw `deepseek-ocr2` command, which wrote unverified OCR straight
  into narration JSON — the file a narrator writes from, where machine text
  reads as evidence. OCR is reachable only through `panel-transcript`, which
  writes SHA-256-bound values into `<item>/transcript.json`.
- Removed the generic image-export commands (`to-pdf`, `to-pdf-lossless`,
  `convert-images`, `watermark`) and the story/song MCP inline-text bridges and
  manifest path enforcement. `ai-zip` is now `panels-context-pack`.

### Added

- **`manga-review`** — hash-bound crop, narration, and final-video approvals
  stored beside SHA-256 snapshots of exactly what was approved. Any change to a
  source page, panel, narration file, or the output MP4 invalidates the record
  automatically. Enforced in `video`, `video-audio`, `video-audio-indextts`,
  `video-render`, and `video-join`, so a direct subcommand call, a background
  job, and an MCP call all hit the same gate.
- **`manga-rights`** — the manifest that authorizes publication: source URL,
  edition, language, creator, publisher, permission basis, allowed chapters,
  attribution, translation provenance, voice consent, music licences, thumbnail
  source panels, and platform-safety scans. It **fails closed**, and rejects the
  two most common wrong beliefs explicitly: that a reachable webtoon page
  implies a licence, and that attribution or a disclaimer substitutes for
  permission.
- **`panel-decisions`** — every cropped panel must be narrated or carry a
  hash-bound omission decision from a fixed vocabulary. The previous "confirm
  none is a story panel" warning recorded nothing, so a dropped story panel and
  a skipped credits page looked identical in every report.
- **`video-quality`** — measures the *encoded* deliverable rather than the
  pre-encode filter: integrated loudness, true peak, A/V drift, black and frozen
  frames, long silence, stale renders. Extracts full-resolution frames for the
  crop-readability and face/bubble-clipping pass no detector performs.
- **`workspace-layout`** — reports every resolved persistent root and whether it
  stays inside the workspace; `doctor` now warns when one escapes.
- **`video_pipeline/narration_contract.py`** — one strict schema every consumer
  validates through: basenames only (no separators, traversal, drive or UNC
  paths), resolved containment inside `panels/`, case-insensitive filename *and
  stem* uniqueness across `intro.json` + `narration.json` combined, rejected
  unknown properties, and bounded `motion` / `pause_after_ms` values with stable
  unique `beat_id`s.
- **TTS provenance sidecars** — every generated WAV gets a `<name>.wav.json`
  recording the normalized narration digest, beat/panel identity, engine, model,
  revision, voice, speaker-WAV digest, language, speed, and settings. A take is
  reused only when all of them match; otherwise it is archived and regenerated.
  "Skip if the file exists" previously shipped last week's sentence in last
  week's voice, and only watching the whole video could catch it.
- Script-level narration lints: duplicate and near-duplicate lines, repeated
  consecutive openings, "Then…" inventory style, meta phrasing (*the panel
  shows*, *we can see*), and beats too short or too long. Reported as warnings,
  because whether a repetition is a tic or a refrain is an editorial call.
- `docs/manga-quality-design.md` — what is automated, what is advisory, and what
  requires a human, with the reasoning for each.

### Changed

- **Thumbnails are built from manga panels, end to end, and the image-generation
  path is gone for good.** `thumbnail-candidates` scores every cropped panel in
  a batch (detail, ink coverage, shape against 16:9, resolution) and renders
  numbered contact sheets, so an agent opens twenty full-resolution candidates
  instead of two thousand — and the ranking is explicitly a proposal, the same
  standing as MAGI's panel boxes, because no pixel statistic knows which panel
  carries the reversal the title promises. `thumbnail-compose` grew the three
  layouts the reference thumbnails actually use: **speech bubbles** (dark bubble
  with white brush lettering for a spoken hook, or light with black text),
  a **chapter badge** pinned to a corner, and a **split** before/after canvas
  from two panels — alongside the existing hook blocks and block arrows.
  `--preset label-arrow|bubble|split` gives a worked starting spec, since
  writing coordinates blind cost two or three render-and-look rounds before
  anything was even roughly placed. `--check` reports the mechanical faults an
  agent cannot see in a JSON spec (text off-canvas, type under 44 px, elements
  stacked on each other, collisions with YouTube's duration overlay) and exits
  3. It stays deliberately narrow: it cannot tell whether the crop cuts a face
  in half or whether the composition reads as a sexualized minor, and a linter
  that pretended to would be worse than none, because it would be trusted.
- **`title-check`** — recap titles against the house pattern:
  `<STATUS or PREMISE> + <REVERSAL> [+ CONSEQUENCE] [(range)] - <Manga|Manhwa>
  Recap`. Checks length against YouTube's 100-character limit, the recap suffix,
  all-caps shouting, emoji, punctuation spam, and chapter-range shape;
  `--pattern` prints the formula and worked examples. Calibrated against the
  titles this channel has actually published, and the test suite pins them:
  every shipped title must pass with no warnings, because a check that nags
  about known-good work teaches an agent to ignore its output. Shape only —
  a title that passes can still be a lie, and truthfulness stays a reviewer
  judgement.
- Removed the last references to image generation: the orphaned
  `z-image-turbo` tool env (35 GB) and its model cache, the `zimage` mentions in
  `thumbnail-compose`'s own help and in the workboard GPU note, and the
  `/z-image-turbo/` ignore rule. The base pixels of a thumbnail are always
  approved panel art, because generated key art promises art the video does not
  contain.
- **One folder for everything produced, and deleting it is the fresh start.**
  Every downloaded or generated file now lives under `<workspace>/data/`
  (`library/`, `audio/`, `audio_faded/`, `output/`, `review/`, `work/`), and
  the re-downloadable machinery moved to `<install>/runtime/`
  (`tools/`, `cache/`, `state/`, `secrets/`). Before, production state landed
  in loose top-level folders resolved against the *current directory* while
  tool envs and caches hid in a dotted `.mangaeasy/`; "start over" meant
  knowing which seven folders to remove and which one to spare, and running a
  command from the wrong directory quietly started a second library tree
  somewhere else. The split is deliberate in both directions: production state
  must be inside `data/` or the promise is false, and the 80 GB of tool
  environments must be outside it or a fresh start costs a re-download.
  `mangaeasy/layout.py` is the single source of truth; `workspace-layout`
  reports where every root actually resolved and fails `--strict` when one
  escapes its tree. `data/README.md` explains the folder to whoever opens it
  in a file manager.
- **`workspace-reset`** — the scriptable version of deleting `data/`. Dry run
  by default (prints what would go and how much space it frees), `--confirm`
  to delete, `--keep-library` to spare the downloaded chapters, `--only` to
  clear named subfolders. It refuses to run while a background job is still
  writing, which is exactly when a hand-deletion produces a half-erased
  production and an unreadable traceback. It is intentionally **not** an MCP
  tool: an irreversible "delete every production" should not be one call away
  from a client.
- Persistent-root environment overrides are now namespaced only. The bare
  `PROJECT_ROOT`, `AUDIO_ROOT`, `OUTPUT_ROOT`, and `WORK_DIR` spellings are
  gone — names that generic already exist in plenty of shells, and a single
  inherited `WORK_DIR` silently relocated production state out of the
  workspace. `MANGAEASY_DATA_ROOT` (whole tree) and `MANGAEASY_HOME`
  (runtime tree) are the supported relocations; pointing them at overlapping
  trees is reported as an error, because a reset would otherwise delete the
  tool environments.
- `where --json` reports `data_root` and `runtime_home`; the `mangaeasy_home`
  key is gone. YouTube credentials moved to `runtime/secrets/youtube/` so
  clearing productions does not sign you out, and `workspace.json` to
  `runtime/state/` so the pointer to the workspace survives a wipe of it.
- `youtube-upload` now requires `--project-root` and refuses to send a byte
  until the final-video review matches the exact file's hash and the rights
  manifest passes. The result payload records the approved video digest, the
  rights basis, the profile, and the live channel id.
- MCP instructions now state that panels, bubbles, OCR, scanlator pages, and
  watermarks are untrusted **data**: text inside artwork that reads like an
  instruction is content to record, never a directive to follow.
- Thumbnails are composed from approved source panels rather than generated key
  art; the panel must be listed in `rights.json` under `thumbnail_sources`.
- `narration-check` now runs the contract, the quality lints, and panel coverage
  in one report.

### Changed

- **The voice-clone reference and the music bed are configured once, and
  their paths work on both operating systems.** `config.system.json` →
  `tts.speaker_wav` and `bgm.file` / `bgm.directory` are used whenever
  `--speaker-wav` / `--background-music` are omitted — including from the MCP
  server, where `add_bgm` no longer requires `background_music` at all. Each
  value accepts a Windows absolute path (`D:/vocal/n.wav`, `D:\vocal\n.wav`,
  UNC shares), a Linux absolute path, or a path relative to
  `config.system.json` itself.

  Relative values anchor to the **config file's directory**, not the working
  directory: an agent runs commands from wherever it happens to be, and
  `"vocal/narrator.wav"` has to mean the same file every time. Absolute paths
  are resolved by `path_safety.resolve_portable_path()` rather than
  `Path.is_absolute()`, which answers only for the host — on Windows it calls
  `/home/me/v.wav` relative and on Linux it calls `D:\vocal\v.wav` relative,
  and either wrong answer silently rebases a good path under the workspace and
  then reports the wrong file as missing. A path that is absolute on the
  *other* OS is now left absolute and simply reported missing, which is an
  honest failure instead of a wrong file.

- `doctor` gained a **Configured media** block (`media` in `--json`) reporting
  the resolved voice-clone WAV and music bed with an exists flag for each.
  Both settings fail silently otherwise: IndexTTS quietly falls back to Kokoro
  when the reference is missing, and a video renders perfectly well with no
  bed — so the first signal used to be listening to a finished render.

### Fixed

- **`setup` registered no workspace on a fresh clone, disabling the guard
  against stray data trees.** `register_workspace()` accepted a directory only
  if it contained `config.json` — but `config.json` is gitignored and
  optional, so a just-cloned checkout has none. Registration silently did
  nothing (no marker, no message), and every later command run from another
  directory resolved its data root to *that* directory, which is precisely the
  second-library-tree incident the registration mechanism exists to prevent,
  reintroduced by the check meant to guard it. Found by cloning onto a wiped
  disk and following `docs/setup.md` literally: after a clean `setup`,
  `mangaeasy where` run from `C:\Users\me` reported
  `data_root: C:\Users\me\data`. A workspace is now recognised by any of three
  signals (`config.json`, an existing `data/`, or a mangaEasy source
  checkout), `setup` creates `data/` before registering so the signal exists,
  and a failure to register now prints a loud warning instead of passing
  silently.
- `config.system.example.json` advertised `video` (resolution, fps, encoder),
  `audio`, `watermark`, and `process_panels` sections that **no code reads** —
  copying the example and setting `video.fps` did nothing, silently. The last
  two were leftovers from commands deleted in 3.0.0. The example now carries
  only the six sections every `load_system_config()` call site actually
  consumes, and says so.
- `docs/setup.md` understated the install budget by more than half: the
  per-tool table claimed ~18 GB total against a measured 30 GB of tool envs
  plus ~17 GB of `uv` build cache. It now states real on-disk sizes and the
  ~50 GB free-space requirement, and points at `uv cache prune` for reclaiming
  the cache.
- `docs/install.md` still described the pre-3.0 single-folder model and never
  mentioned `data/` or `runtime/`; `run.sh` / `run.bat` still advertised the
  "MCP router" removed in 3.0.0.
- `video-quality` loudness measurement was silently discarded by ffmpeg's
  `-loglevel error`, which suppresses `loudnorm`'s JSON summary, and digital
  silence (`-inf`) would have serialized as invalid JSON.

## 2.2.4 — 2026-07-26

### Added

- Added `MCP_CONFIG.md` with ready-to-paste Windows MCP client blocks for a
  source checkout or globally installed `mangaeasy` command.

### Changed

- Manga crop and narration review are now explicit `review_required` states
  (exit code 3). MAGI no-detection and automatic near-full-page boxes no
  longer become production crops; every source overlay, crop, and narration
  pairing must be opened by a vision-capable reviewer.
- Manga MCP build tools now require an explicit true
  `manual_review_confirmed` assertion after that visual pass. Split reports
  enumerate original source images and full-resolution production crops, and
  regenerated review runs remove stale surplus artifacts.
- Manga MCP uploads require a separate `final_video_review_confirmed` assertion
  after watching and listening to the complete export at normal speed.
- DeepSeek OCR is documented and surfaced as optional, unverified
  cross-evidence. Transcript rows are SHA-256-bound to their exact crop bytes
  so a same-name re-crop invalidates stale OCR instead of silently reusing it.
- Strengthened manga recap authoring rules around current-panel grounding,
  speaker attribution, causal clarity, pronouns, varied sentence openings,
  chronology, and unsupported/future claims. Final publication now requires a
  complete normal-speed watch/listen pass.
- Raised production video defaults from NVENC `p1` / AAC 128 kbps to NVENC
  `p5` / AAC 192 kbps, with valid libx264 preset mapping for CPU fallback.

### Removed

- Removed the bundled Gemma 4 local-LLM runtime and its `llm`, `crop-qa`,
  `characters`, `narrate-auto`, and `manga-auto` command/MCP surfaces. Manga
  crop review and narration now remain explicit visual-review tasks, with
  `work-note` carrying cast, speaker, crop, and handoff decisions between
  agents.
- Removed per-entry TTS emotion modulation and the `--emo-alpha` /
  `--no-emotion` CLI and MCP controls. Legacy `emotion` keys in narration JSON
  are now inert metadata; use `--overwrite-audio` to replace previously
  generated takes when needed.

## 2.2.3 — 2026-07-21

### Added

- **`work-todo` — shared session todo list for cross-model handoff.** The
  scenario it's built for: one LLM runs out of budget/context mid-batch and a
  different one (different vendor, no shared chat memory) needs to resume as
  if it were the same worker. `work-status`, `work-claim`, and `work-note`
  already made the filesystem and a shared notebook the source of truth
  instead of any one agent's memory; `work-todo` adds the missing piece —
  plan-level next steps that aren't derivable from disk (batch scope, redo
  requests, things to confirm before publishing). Storage is an append-only
  event log (`todo.jsonl`, same durability model as `notes.jsonl`): add /
  start / done / reopen / remove, ids never reused. Open todos now also
  surface directly in `work-status`'s report (capped at 10) so the existing
  "run this first" resume command already shows them. Exposed as the
  `work_todo` MCP tool alongside the other four `work_*` tools. See
  `docs/multi-agent.md`'s new "Switching LLM providers mid-project" section
  for the full handoff recipe (set `MANGAEASY_AGENT` per model, leave a
  `handoff`-topic note before a session ends).

## 2.2.2 — 2026-07-18

### Changed

- **Background music default lowered −26 → −28 dB.** −26 read as loud and
  fatiguing over a full long-form recap watch; −28 keeps the bed felt but
  comfortable in the background (a punchier or sparser edit can move back up
  to −26…−22). Updated `defaults.py`, both `config.system*.json` templates,
  every `--music-volume-db` help string, and the stray `-25.0` dataclass
  fallback in `long_video_builder.py` that had drifted from the real default.

### Added

- **TTS delivery rules, enforced by `work-qa`.** IndexTTS2 renders
  scream/shout-intensity `emotion` words ("screaming", "shouting", "yelling",
  "shrieking"...) as actual screaming far more often than not — annoying and
  usually not even the right read of the panel. `emotion_lint` now rejects
  those words outright (a calmer synonym like `"tense"`/`"fearful"` still
  conveys the moment). A new `narration_delivery_lint` flags narration text
  that spells out a laugh or scream phonetically ("ha ha ha", "gyahahaha",
  "aaaargh") instead of describing it in prose ("she laughed") — TTS
  mispronounces or shouts spelled-out SFX since it isn't a real word, but
  handles real interjections ("hmm", "even though...") fine. Both rules are
  documented in `narration.md` and baked into `narrate-auto`'s drafting
  prompt so auto-drafted narration follows them from the start.
- **Strict panel-crop framing rule for `page-split`/`crop-qa`.** A crop must
  fully contain its panel — never a partial edge, never the whole page
  standing in for a panel with its own border. Boxes far taller than wide
  (`>= TALL_PANEL_ASPECT_RATIO`, reported as `tall_panel_boxes`) usually
  swallowed gutter whitespace instead of hugging the art; the rendered video
  frame is 16:9 landscape, so a needlessly tall crop just shrinks to an
  unreadable sliver once fit to it (1:1-ish crops are fine — this only flags
  real excess gutter, not a panel that is genuinely that tall). `crop-qa`'s
  Gemma-vision page reviewer now checks for this and for incomplete crops
  before proposing an `--overrides` fix.

## 2.2.1 — 2026-07-18

### Fixed

- **Blank terminal windows stopped popping up — for real this time.** 2.1.0
  hardened every `subprocess` spawn, but two paths remained and were
  reproduced with a window-watching probe:
  - Detached background jobs used `DETACHED_PROCESS`, and the supervisor argv
    is the venv `python.exe` — a launcher shim that respawns the base
    interpreter as a child. Console-less shim → the respawn allocates a fresh
    console → Windows 11 (default terminal = Windows Terminal) shows it as a
    visible blank terminal for the whole job. Jobs now detach with their own
    hidden console (`CREATE_NO_WINDOW` + `CREATE_NEW_PROCESS_GROUP`), which
    the venv respawn and all job children inherit: same parent-death
    survival, no window. Regression-tested.
  - `install-tool`'s winpty PTY allocates a console for its agent, which can
    also surface as a visible terminal. Pipe mode (windowless, same log
    lines) is now the default; set `MANGAEASY_INSTALL_PTY=1` to opt back
    into PTY progress rendering.
- `install-tool` skipped the model download entirely for tools that declare
  their snapshot only via `extra_models` (gemma-4 shipped without weights).

## 2.2.0 — 2026-07-17

### Added

- **Local LLM: Gemma 4 E4B** (`mangaeasy install-tool gemma-4`,
  Apache-2.0). A revision-pinned GGUF snapshot (Q4_0 + vision projector,
  ~6 GB) served by a pinned llama.cpp release binary (Vulkan on GPUs, CPU
  everywhere else; `MANGAEASY_LLAMA_SERVER` overrides). Raw access via
  `mangaeasy llm` (text + images, JSON-schema-constrained output,
  batch manifests). Installed by default with `setup --mode manga-video`.
- **Assist commands** (`mangaeasy/assist/`) so small or text-only driver
  agents could produce vision-grounded manga drafts in that release:
  - `crop-qa` — Gemma-vision review of every flagged crop location (webtoon
    forced cuts/short panels, paged page overlays); prints the exact
    `webtoon-override` / `--overrides` fix per FIX verdict; exit 3 until clean.
  - `characters` — per-project `characters.json` cast registry (names,
    aliases, appearance, role) that grounds narration and speaker
    attribution; `--auto-draft` proposes it from sampled panels + OCR
    (always `draft: true` for review).
  - `narrate-auto` — grounded `narration.json` drafts from panel images +
    OCR + the registry, with banner skipping and a story-so-far chain; runs
    `narration-check` + review sheets and always exits 3 (review before TTS).
  - `manga-auto` — one-command orchestrator: download → style-detect → the
    correct splitter → crop-qa → panel-transcript → characters +
    narrate-auto (`--stage prep`, ends at a review checklist), then
    `--stage build` for TTS/render/join/normalize → validate → work-qa.
    Never publishes.

### Fixed

- **`style-detect` now recognizes pre-sliced webtoons.** Hosts (MangaDex
  included) often serve webtoons cut into page-height chunks — page-shaped
  ratios that the aspect bands alone misread as "paged". A shared modal
  width with strongly varying heights (`height_cv`) now yields a "webtoon"
  verdict; genuinely uniform page scans still detect as "paged".
- **Wrong-splitter runs are now blocked.** `webtoon-split` and `page-split`
  re-measure each item's pages and refuse a confident opposite verdict
  (e.g. a webtoon fed to the MAGI paged splitter — a real production
  incident by a small driver agent), naming the correct command;
  `--force-style` overrides for deliberate mixed-format items.
- **Commands run from a wrong cwd no longer scatter `library/` trees.**
  `setup` registers the workspace (`<data>/workspace.json`); workspace
  resolution now tries `MANGAEASY_PROJECT_ROOT` → a cwd containing
  `config.json` → the registered workspace → a source checkout's own root →
  cwd. `where --json` reports `workspace_root`, and `download` prints its
  resolved destination (with a loud warning outside any workspace) before
  any network work.

## 2.1.0 — 2026-07-17

### Fixed

- **Blank console windows no longer pop up on Windows.** Every child process
  (ffmpeg, uv, git, external tool envs) now spawns through
  `mangaeasy.runtime.run/popen`, which applies `CREATE_NO_WINDOW`
  whenever the parent has no visible console — detached background jobs and
  MCP servers started by an editor were the common triggers. Linux/macOS are
  unaffected (the wrappers add nothing there). A repository-hygiene test now
  forbids raw `subprocess.run/Popen` calls outside `runtime.py`.
- `mediaconductor index-tts` pointed at `audio/tts.py`, a script deleted with
  the GUI in 2.0 — the command always failed. It now launches the real batch
  pipeline (`audio/tts_pipeline.py`) and documents the pass-through flags.

### Changed

- **The Python package is now `mediaconductor`** (was `mangaeasy`), finishing
  the 2.0 rename. Entry points, env vars, and stdout markers follow:
  - Env vars are `MEDIACONDUCTOR_*`; legacy `MANGAEASY_*` values are mirrored
    at startup and keep working.
  - Machine markers are `MEDIACONDUCTOR_RESULT` / `MEDIACONDUCTOR_PROGRESS`;
    scanners still accept the legacy spellings (tool scripts copied into
    existing external envs print them).
  - The data dir is `<app_root>/.mediaconductor` for fresh installs; existing
    `.mangaeasy` dirs (tool envs, models) are detected and kept — nothing is
    re-downloaded. `where --json` reports `data_home` (new) alongside
    `mangaeasy_home` (legacy key, same value).
  - The `mangaeasy` command remains a compatibility alias.

- Manga-video production now defaults to separate `audio_faded` per-panel
  derivatives with symmetric 8 ms edge fades; raw TTS WAVs remain untouched.
  The long-video order is join → BGM → one final two-pass whole-mix normalize
  at −14 LUFS / −1.5 dBTP. Any BGM change requires a new final normalization.
  Narration gain now has a single owner instead of being applied once during
  join and a second time during BGM remixing.
  Final normalization reserves AAC true-peak headroom so the encoded
  deliverable, not only the pre-codec filter output, stays within −1.5 dBTP.
- Clarified that `video-validate` is a structural gate and that visual,
  narration-timing, edge-click, and final loudness/true-peak QA remain separate
  release checks.
- Documented replacement publishing: upload-first remains the safe default;
  deletion-first is allowed only on an explicit user request and requires
  profile/channel/video verification, publish-record replacement, and a final
  live-listing check.

## 2.0.0 — 2026-07-15

### mangaEasy platform

- Renamed the product, Python distribution, primary CLI, release artifacts,
  and MCP identity to **mangaEasy**. The `mangaeasy` command and Python
  package remain compatibility surfaces for 2.x.
- Added isolated Manga Video, AI Story, and Song Video modes, each with its
  own small MCP catalog, setup profile, Codex-compatible skill, and reference
  documentation.
- Added schema-v2 AI Story projects with immutable character/environment
  cards, ordered scene-state ledgers, deterministic prompt locks, reference
  sheets, digest-bound generation provenance, and explicit visual/video/rights
  gates before publishing.
- Added Song Video projects with ACE-Step 1.5 generation, maintained Demucs
  separation, WhisperX timing against canonical lyrics, minimalistic-sky art,
  and the bundled Edo SZ lyric treatment with a small shadow and line fades.
- Added production/release validation for source, wheel, sdist, frozen CLI,
  and mode-scoped MCP handshakes. Removed tracked sample music and voice media.
- Added an MCP workspace boundary with repeatable `--allow-root` values and a
  startup-directory default, including nested typed jobs and manifest-linked
  media paths.
- Hardened direct CLI child-path inputs: project/MangaDex names, chapter
  folders, panel source/output subpaths and prefixes, and archived-run names
  now reject absolute paths, traversal, reserved names, and non-portable
  characters while preserving valid Unicode and internal spaces.
- Added isolated named YouTube account profiles, allowing each production mode
  to publish to a distinct verified channel or reuse one profile across modes;
  the original single-account files remain the compatible `default` profile.
  One shared Desktop-app client can authorize every profile, and live commands
  automatically open browser re-consent/retry unless `--no-auto-auth` is set.

### Added
- **Background job runner** — `job-start <command> [args…]` runs any command
  as a detached, supervised background job (state + log under `<work>/jobs/`);
  `job-status <id> --json` reports running/succeeded/failed/**orphaned**
  (dead supervisor — machine sleep/kill) with the last `MANGAEASY_PROGRESS`,
  the parsed `MANGAEASY_RESULT`, and a log tail; `jobs --json` lists all.
  Exposed over MCP as `job_start`/`job_status`/`job_list` — long-running MCP
  tools now direct callers there instead of blocking `tools/call` for hours.
- **`commands --json --full`** — the machine-readable catalog now includes
  each command's argument schema (flag, type, required) and a `long_running`
  marker, ending the one-`--help`-per-command discovery loop for agents.
- **`mangaeasy/command_spec.py`** — single declarative table of command
  schemas; the MCP server and `commands --json --full` both render from it,
  so the two surfaces can no longer drift (the MCP server previously kept a
  hand-maintained private copy of every schema).

### Changed
- **`--gpu-workers` is clamped to 4 in code** (was a docs-only rule); the
  tested-unsafe values warn and clamp, `MANGAEASY_UNSAFE_GPU_WORKERS=1` opts
  out on tested hardware.
- **Config loaders raise `ConfigError` instead of `sys.exit`** (the CLI
  dispatcher renders it as `[ERROR] …`, exit 1) and `mangaeasy/config.py` no
  longer mutates `HF_HOME`/`TORCH_HOME` at import time; `tts_pipeline` now
  respects the tool-env cache pin instead of overriding it with a second
  cache at `<cwd>/.hf_cache`.
- **Namespaced root env vars** — `MANGAEASY_ITEMS_ROOT`/`MANGAEASY_AUDIO_ROOT`/
  `MANGAEASY_OUTPUT_ROOT`/`MANGAEASY_WORK_DIR` (bare legacy names still
  honoured).
- **MCP hardening** — JSON reports are parsed by scanning from the last line
  up (a stray print can't blind the parser); truncation keeps head+tail.
- **Docs diet** — CLAUDE.md cut from ~32 KB to ~9 KB (incident lore moved to
  `docs/history/incidents.md`); `START_HERE.md` retired into
  CLAUDE.md/AGENTS.md; stale references (Flask assets, `narration.backup.json`,
  removed packages) purged from live docs.

### Removed
- **Dead GUI-era dependencies and assets** — flask, playwright, cloudscraper,
  curl-cffi, pydub, and beautifulsoup4 were required dependencies with zero
  imports anywhere in the package (leftovers of the deleted GUI/scraper era);
  the unused `[ml]`/`[whisper]`/`[all]` extras (AI deps live in the isolated
  tool envs, never the main env); `mangaeasy/assets/templates/` +
  `mangaeasy/assets/static/` (six orphaned Flask editor pages); the stale
  duplicate `mangaeasy/assets/config/` examples. Classifiers updated
  (Beta, no Flask, Developers).
- **Dead pre-Electron web control center** — `mangaeasy/assets/templates/app.html`,
  its 13-file JS bundle (`static/js/app/*.js`), `static/css/app.css`, and the
  vendored `static/vendor/xterm/` (xterm.js terminal) were leftovers from the
  NiceGUI/pywebview control center that `mangaeasy app` replaced with the
  Electron desktop app (`desktop/`) — the replacement module's own docstring
  already said "The NiceGUI/pywebview GUI this replaced has been removed,"
  but these static assets were never actually deleted. Confirmed unreachable
  (no Flask route in the package renders `app.html`; every other web tool's
  `render_template()` call targets its own distinct template) before removal.

### Added
- **Thumbnail-generation guidance in the recap playbook** — Phase 9 now spells
  out how to write the prompt for high-energy generated (Z-Image Turbo) recap
  key art with a strong focal subject and mobile-readable composition, with a
  non-negotiable safety bound baked into
  the prompt-writing rules themselves: every character drawn as a visibly
  adult, fully clothed (revealing-but-not-explicit is the ceiling), no
  nudity/transparent clothing/explicit content/minor-coded characters, and a
  mandatory-checks item to review every generated variant against those
  rules before picking one — a thumbnail strike risks the whole channel.
- **Z-Image Turbo image generation** — `mangaeasy install-tool z-image-turbo`
  provisions Alibaba's Apache-2.0 text-to-image model (~33 GB) in an
  isolated env, and `mangaeasy zimage --prompt "..." --output out.png`
  generates images (thumbnails, backgrounds, channel art). Hardware is
  handled automatically: full bf16 on 16 GB+ NVIDIA GPUs and Apple
  Silicon, NF4 4-bit quantization on 8–12 GB NVIDIA cards (~24 s/image on
  an RTX 3060), CPU offload/fp32 fallbacks below that. Also exposed as the
  `generate_image` MCP tool. See docs/external-tools.md.
- **`mangaeasy download --chapter N` / `--chapters 0-12 14 20.5`** —
  download any chapter (or a whole batch) without editing config.json.
  Batches fetch the MangaDex feed once, skip chapters that don't exist in
  the requested language (with a warning and a final summary instead of
  aborting), and when several scanlations upload the same chapter number,
  the fullest version (most pages) is picked instead of feed order.
- **Music bed conditioning + ducking in `video-add-bgm` (all default-on).**
  The background-music mix now matches professional voiceover practice
  instead of a flat gain:
  - **Dynamics compression** — the bed's own loudness range is compressed
    (the production track went from LRA 7.9 → 3.4 LU) so it sits at a
    *constant* level under the voice instead of swelling and receding on its
    own, which was the main reason the bed still sounded "unmixed."
    `--no-condition-bed`.
  - **Vocal-band EQ carve** — a gentle dip in the 2–5 kHz
    speech-intelligibility band so the music masks the voice less.
    `--no-eq-carve`.
  - **Sidechain ducking** — the music dips a few dB under the narration and
    breathes back up in the pauses (default ratio 2, tuned so wall-to-wall
    narration doesn't just make the music uniformly quiet). Was opt-in
    `--duck`; now on by default with `--no-duck` to disable.
  - **Limiter fix** — the post-mix `alimiter` no longer runs with its
    default `level=true`, which auto-normalized the output back toward
    0 dBFS and fought the gain staging.
- **Music loudness alignment in `video-add-bgm`** — the (conditioned) music
  stem's integrated loudness is measured (ffmpeg ebur128) and pre-gained to
  the narration reference before `--music-volume-db` is applied, so the
  offset is a true LU separation regardless of how hot the track was mastered.
  Disable with `--no-music-loudnorm`. The production default is **−26 dB**
  for dense, wall-to-wall narration (recaps); sparser voiceover may use a less
  negative value after listening and measuring.

### Fixed
- `mangaeasy doctor` reported `gpu_backend: "cpu"` (and the app's Setup tab
  showed "CPU only") on CUDA machines whenever the main env had no torch —
  which is the normal state, since torch lives in the isolated tool envs.
  GPU capability is now probed at machine level (nvidia-smi / Apple
  Silicon), matching what `install-tool` and TTS auto-selection actually
  use; `cuda_device` is filled from nvidia-smi when torch isn't available.

### Added (earlier)
- **`library/<name>/manga.json`** — `mangaeasy download` now records where
  each manga came from: source site, canonical MangaDex title URL, the
  original link you pasted, the canonical title (fetched from the API once,
  then cached), and per-chapter download info (chapter UUID, language, page
  count, timestamp). Previously the link only lived in `config.json`'s
  *current* download target, so it was lost as soon as you moved on to the
  next manga. Existing projects get the file on their next `download` run.
- `mangaeasy library-list` surfaces it: the human view prints `title:` and
  `source:` lines per project; `--json` gains a per-project `manga` field
  (`null` when the file is absent).

## v1.3.1 — 2026-07-03

- Setup tab → YouTube account: the downloaded `client_secret.json` file now
  has its own **Browse client_secret.json…** button (it was a small text
  link before), plus a one-click "Connect with already-attached project"
  button when a project is attached but the account is disconnected.

## v1.3.0 — 2026-07-03

Simpler YouTube project attach + live verification.

### Added
- **Paste-to-attach**: connect your Google project by pasting the Client ID
  and Client secret straight from the Google console — no JSON file needed.
  CLI: `mangaeasy youtube-auth --client-id <id> --client-secret <secret>`;
  GUI: Setup tab → YouTube account now has the two fields + "Attach &
  connect" (the client_secret.json file path still works as before).
- **Live verification**: `mangaeasy youtube-status --verify` (and a
  "Verify" button in the GUI) refreshes the token and queries the channel
  to prove the connection works right now, with a clear error when it
  doesn't. MCP `youtube_status` gained the matching `verify` option.
- Input validation with actionable errors (client-ID format check, both
  values required together).

## v1.2.0 — 2026-07-03

Direct YouTube upload — connect your channel once, then publish finished
videos from the app, the CLI, or an AI assistant.

### Added
- **YouTube account connect** (`mangaeasy youtube-auth` /
  `youtube-status [--json]` / `youtube-logout`, and Setup tab → "YouTube
  account"): browser-based Google consent using your own free OAuth client
  (one-time ~10-minute setup — full walkthrough in `docs/youtube.md`).
  Tokens live in the app's own data folder (`.mangaeasy/youtube/`),
  removable with one click; nothing system-wide.
- **`mangaeasy youtube-upload`**: resumable chunked upload with retry and
  progress, title/description(-file)/tags/privacy/category/thumbnail
  flags, friendly quota/auth error messages, and the standard
  `MANGAEASY_PROGRESS` + `MANGAEASY_RESULT {"video_id","url"}` machine
  contract. Default privacy is **private** (YouTube locks uploads from
  personal, unaudited API projects to private — publish in YouTube Studio).
- **Batch tab → "Upload to YouTube" step**: defaults to your latest joined
  long video, with title (pre-filled), description, tags, and privacy.
- **MCP tools** `youtube_status` and `youtube_upload`; new "Uploading to
  YouTube" section in the AI guide with agent rules (never attempt the
  browser auth; respect quota; don't fight the private lock).
- Dependencies: `google-auth` + `google-auth-oauthlib` (OAuth flow/refresh
  only — the upload itself is plain `requests` against YouTube's resumable
  protocol).

## v1.1.0 — 2026-07-03

AI-assistant / scripting release: the whole pipeline is now drivable by any
AI agent (or shell script) through a documented, machine-readable CLI
contract — isolation story unchanged.

### Added
- **`docs/ai-guide.md`** — the complete operating manual for AI assistants
  and scripts (install modes, data anatomy, recipes, output contract,
  safety rules), plus a root `AGENTS.md` pointer that agent tools
  auto-discover. A test cross-references the guide against the real command
  catalog so the docs can't rot silently.
- **`mangaeasy mcp`** — a built-in MCP stdio server (pure stdlib, no new
  dependencies) exposing 13 typed tools (doctor, where, library_list,
  video_check, audio_audit, generate_audio, render_videos,
  build_long_video, add_bgm, run_full_pipeline, …) to any MCP-capable
  assistant. Register with `claude mcp add mangaeasy -- mangaeasy mcp`.
- **`mangaeasy commands --json`** — machine-readable catalog of every
  command; **`mangaeasy where --json`** — this install's resolved
  data/tool paths (the first thing an agent should run).
- **`mangaeasy library-list [--json]`** — list projects and per-item
  readiness (panels/narration/intro/audio) without opening the GUI; handles
  both the item-pipeline and legacy chapter layouts.
- **`--json` output** for `video-check`, `video-validate`,
  `video-audio-audit`, and `tools` (joining the existing `doctor` and
  `audio-takes-list`).
- **`MANGAEASY_RESULT {"outputs": [...]}`** — a stable machine-parsable
  final line on successful generation commands (`video`, `video-render`,
  `video-join`, `video-add-bgm`, `video-normalize-audio`) so callers find
  the produced files without scraping log text.
- Setup → About now shows the exact CLI command for this install (with a
  copy button including `MANGAEASY_ROOT`), so agents can share the GUI's
  data and installed tools.
- Agent-style end-to-end test: fixture project → `video-check --json` →
  `video-render` over plain pipes, asserting the result marker.

### Fixed
- **Piped output no longer crashes on Windows**: stdout/stderr are forced
  to UTF-8, so running any command from a script/agent (where stdout is a
  pipe defaulting to cp1252) can't die on characters like "−".

## v1.0.0 — 2026-07-02

First production release. Focus: the downloaded app now actually works as an
installed product on all three platforms, with an honest isolation story.

### Fixed
- **App data location was broken in every packaged build.** The Windows
  portable exe wrote its data (tool environments, models — gigabytes) into a
  temporary folder that changed every launch; on macOS/Linux the app tried to
  write inside the read-only app bundle/AppImage. Data now lives in:
  next to the `.exe` (Windows portable), `~/Library/Application
  Support/mangaEasy` (macOS), `~/.local/share/mangaEasy` (Linux). Electron's
  own caches are kept inside the same folder, so deleting it removes every
  trace.
- **Release assets were always labeled `0.1.0`** regardless of the actual
  version. The build now stamps the git tag's version everywhere and fails if
  the sources disagree.
- **"ffmpeg is bundled" was false** — the release pipeline downloaded ffmpeg
  at build time and then shipped without it. The app now offers a one-time
  ~100 MB "Download core tools" on first launch (Setup tab), with download
  progress, on all three platforms including macOS (no more `brew install`
  requirement).
- Editor launches no longer give up after 15 s (slow antivirus-scanned first
  starts were failing) and no longer leave an orphaned server running on
  timeout.
- Backend JSON replies (doctor, audio takes) are parsed robustly instead of
  breaking on any stray warning line.
- The desktop app's dev-mode backend resolution now works on macOS/Linux
  checkouts, not just Windows.

### Added
- Resizable terminal pane (drag the divider; double-click resets) and
  terminal font-size controls (A− / A+), both remembered across restarts.
- Window size/position remembered across restarts.
- Post-job status line: a failed job shows its exit code prominently instead
  of only in the terminal scrollback.
- Update check: the app notifies (non-intrusively) when a newer release is on
  GitHub. Setup tab → About also checks on demand.
- About section in Setup: version, where the app's data lives (with an Open
  button), and an "Open logs folder" button.
- Main-process log file (`.mangaeasy/logs/main.log`) and a renderer error
  boundary — UI crashes show an error page with details instead of a blank
  window.
- Test suite (pytest) for the pipeline's pure logic, ruff linting, and a CI
  workflow that runs lint/tests/typecheck/build on every push on all three
  OSes. The release build smoke-tests the frozen backend before packaging.
- Intel-mac build (best-effort) alongside Apple Silicon.

### Changed
- Release artifacts renamed to one convention:
  `mangaEasy-<version>-<os>-<arch>[...]`.
- The `.deb` package metadata (maintainer, category) is now real.
