# MediaConductor

> An agent-native toolkit for manga, manhwa, and webtoon recap videos.

[![CI](https://github.com/tawhidUnhappy/MediaConductor/actions/workflows/ci.yml/badge.svg)](https://github.com/tawhidUnhappy/MediaConductor/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%E2%80%933.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/core-MIT-green)](LICENSE)

MediaConductor (formerly **mangaEasy**) is a production-oriented CLI and MCP
server that lets an LLM acquire manga chapters, crop them into panels, verify
those crops by eye, narrate them against the artwork, synthesize, render, and
explicitly publish a recap video. It has no GUI. Heavy AI projects run in
separate `uv` environments so incompatible Torch/CUDA stacks never enter the
small core environment.

```text
download / import            MangaDex or your own chapter files
→ crop                       webtoon strips or paged manga (MAGI)
→ VERIFY CROPS               every overlay and crop, recorded as a review
→ narrate                    from the panels; OCR is a cross-check, not a source
→ account for every panel    narrated, or a recorded omission decision
→ TTS                        Kokoro or IndexTTS, provenance-bound
→ render → join → BGM        one final whole-mix normalize
→ measure the encoded file   loudness, drift, black/frozen frames, silence
→ FINAL VIDEO REVIEW         recorded against the exact MP4 hash
→ rights check → upload      fails closed if permission is unresolved
```

The parts a machine can check are checked automatically. The parts it cannot —
is this crop readable, is this line attributed to the right speaker, does this
video hold up — are surfaced as review items pointing at
exact files, and are recorded as approvals bound to the bytes they cover.

## Start from a repository link

An AI agent can set up the complete application from only this URL:

```bash
git clone --depth 1 https://github.com/tawhidUnhappy/MediaConductor.git
cd MediaConductor
uv sync
uv run mediaconductor modes --json
uv run mediaconductor setup --mode manga-video
uv run mediaconductor doctor --mode manga-video --json
```

Then point the agent to [AGENTS.md](AGENTS.md), which loads one small skill.
`mediaconductor modes --json` also returns the absolute `skill_path`, including
wheel and frozen installations where the skill is bundled inside the package.

Requirements for a source clone are Git and
[`uv`](https://docs.astral.sh/uv/); uv provisions a compatible Python
3.10–3.12 interpreter when needed. `setup` vendors ffmpeg/ffprobe and other
core executables into the application data folder. NVIDIA is optional; CPU
fallbacks work but panel detection and voice cloning are much slower.

Install the command globally instead:

```bash
uv tool install git+https://github.com/tawhidUnhappy/MediaConductor.git
mediaconductor modes
```

`mangaeasy` remains an equivalent compatibility command for existing scripts.
The internal Python import remains `mediaconductor` during the 2.x migration.

## The pipeline

```bash
mediaconductor setup --mode manga-video
mediaconductor commands --mode manga-video --json --full
mediaconductor mcp --allow-root D:/MediaProjects
```

MangaDex acquisition, webtoon or paged-manga crops, visual verification sheets,
source-grounded narration with optional OCR cross-evidence, Kokoro/IndexTTS,
item and long-video rendering, music mixing, thumbnails, QA, and YouTube.

The splitters refuse a confident wrong-format run (webtoon pages into the paged
splitter and vice versa), but crop approval and narration remain visual tasks.
Use verification sheets as indexes, then open every source page/strip overlay
and every actual crop at readable/full resolution. Write narration directly
from each original panel with OCR only as a cross-check. A text-only driver
must hand those steps to a vision-capable agent or human; use `work-note` to
preserve cast, speaker, crop, and handoff decisions between agents.

See [the Manga Video skill](skills/manga-video/SKILL.md) and
[docs/manga-quality-design.md](docs/manga-quality-design.md).

## Review is recorded, never asserted

There is no confirmation flag anywhere in the CLI or the MCP schema. An
approval is a record bound to SHA-256 snapshots of exactly what was approved:

```bash
mediaconductor manga-review crop        --project-root data/library/<P> --items 01 --reviewer NAME
mediaconductor manga-review narration   --project-root data/library/<P> --items 01 --reviewer NAME
mediaconductor manga-review final-video --project-root data/library/<P> --items 01 \
    --video data/output/<P>/<P>_full.mp4 --reviewer NAME \
    --rights-confirmed --voice-consent-confirmed --source-permission-confirmed
mediaconductor manga-review check       --project-root data/library/<P> --items 01
```

Re-cropping a panel, rewriting a line, or re-encoding the MP4 invalidates the
matching record automatically. TTS, rendering, joining, and upload all refuse to
run without current records — from the full pipeline, from a direct subcommand,
from a background job, and from MCP alike. **There is no bypass flag.** The
previous `--review-policy warn` was removed: an escape hatch is what a run under
time pressure reaches for, and an unreviewed render is indistinguishable from a
reviewed one once it exists.

Related gates:

- `mediaconductor panel-decisions` — every cropped panel must be narrated or
  carry a hash-bound omission decision (`credit`, `scanlator_notice`,
  `decorative`, `duplicate`, `sfx_only`, `platform_safety`, `other`).
- `mediaconductor manga-rights` — the manifest that authorizes publication.
  It **fails closed**: a page being reachable on a webtoon site is not
  permission, and neither is attribution or a disclaimer.
- `mediaconductor video-quality` — measures the *encoded* deliverable, not the
  pre-encode filter, and extracts frames for the readability pass.

## MCP server

```bash
mediaconductor mcp --allow-root D:/MediaProjects
```

For ready-to-paste source-checkout and globally installed client blocks, see
[MCP_CONFIG.md](MCP_CONFIG.md).

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "mediaconductor",
      "args": ["mcp", "--allow-root", "D:/MediaProjects"]
    }
  }
}
```

The catalog is the manga catalog. There is no router mode and no `--all-tools`
escape hatch; a tool outside the catalog answers *unknown* rather than
"forbidden", so a removed feature cannot be probed by name. Background jobs
accept a typed MCP tool and a validated argument object — never raw command
lines. Each repeatable `--allow-root` confines direct arguments, nested job
arguments, configured defaults, and review/rights/final-video paths. If it is
omitted, the server allows only its startup working directory. This same-user
stdio boundary reduces accidental filesystem reach; it is not an
operating-system sandbox.

Long-running calls must use `job_start`, then `job_status`:

```json
{
  "tool": "job_start",
  "arguments": {
    "tool": "run_full_pipeline",
    "arguments": {
      "project_root": "D:/MediaProjects/library/Recap",
      "audio_root": "D:/MediaProjects/audio",
      "output_root": "D:/MediaProjects/output"
    }
  }
}
```

Shell-only agents use the equivalent detached runner:

```powershell
mediaconductor job-start --tool run_full_pipeline --arguments-json '{"project_root":"D:/MediaProjects/library/Recap","audio_root":"D:/MediaProjects/audio","output_root":"D:/MediaProjects/output"}'
mediaconductor job-status <job-id> --json
```

`job-status` accepts only the generated id returned by `job-start`. Use
`--jobs-dir` to select a different state root; JSON file paths and traversal
segments are rejected.

For a containerized stdio server, keep application state and media in the
mounted `/data` workspace:

```bash
docker build -t media-conductor .
docker run --rm -i -v D:/MediaProjects:/data media-conductor \
  mcp --allow-root /data
```

The image exposes no unauthenticated network port. Run setup against the same
persistent volume first (`... media-conductor setup --mode manga-video`) so its
isolated tools and model snapshots survive container replacement.

## Self-contained workspace

Everything MediaConductor downloads or generates goes in **one folder**,
`data/`. Delete that folder and the install is factory-fresh — nothing else
needs cleaning up, and nothing you own goes with it:

```text
<workspace>/
  data/                    ← everything produced. Delete it to start fresh.
    README.md              what each folder holds, in plain English
    library/<project>/     downloaded chapters, cropped panels, narration, rights
    audio/<project>/       raw TTS takes + provenance sidecars
    audio_faded/<project>/ render-safe narration derivatives
    output/<project>/      per-item videos, <project>_full.mp4, quality/ reports
    review/                review sheets and evidence
    work/                  jobs, manifests, render scratch — safe to delete any time
  runtime/                 ← kept out of data/ so a fresh start stays cheap
    tools/                 isolated AI environments (tens of GB)
    cache/                 HF, Torch, uv, Triton, Inductor caches
    state/                 which workspace this install points at
    secrets/youtube/       gitignored OAuth tokens
  bgm/  vocal/             your licensed music and narrator references
  config.json  config.system.json
```

`bgm/`, `vocal/`, your config, the installed AI tools and your YouTube login
all live outside `data/` on purpose: starting over should cost you a
re-render, not your music library, an 80 GB re-download, or another OAuth
round-trip.

Start fresh without opening a file manager:

```bash
mediaconductor workspace-reset                 # dry run: what would go, and how big
mediaconductor workspace-reset --confirm       # do it
mediaconductor workspace-reset --keep-library --confirm   # keep the downloads, clear the rest
```

It refuses to run while a background job is still writing, and prints exactly
what it removed. `mediaconductor workspace-layout --json` reports every
resolved root and whether it landed in the right tree; `doctor` warns when one
escapes.

## Isolated external tools

Each tool lives under the managed tools directory with its own interpreter,
dependency graph, caches, adapter, model provenance, and `READY.json`.
`doctor` treats that marker as a local completeness record: an installer-managed
model must still have its model directory and either every declared file or at
least one real payload file outside the Hugging Face metadata cache.

Every model snapshot downloaded by `mediaconductor install-tool` is locked to
an immutable Hugging Face commit and checked against a required-file allowlist.
Source checkouts are also commit-pinned. Kokoro and MAGI still obtain model
weights on first use, so those paths are explicitly documented as
non-reproducible follow-ups.

| Tool | Role | Source strategy |
|---|---|---|
| Kokoro 82M | CPU-friendly narration | pinned optional source clone; model weights resolve on first use |
| IndexTTS 2 | voice-cloned narration | pinned source commit and HF model revision |
| MAGI v3 | manga panel detection | pinned optional source clone; remote-code model resolves on first use |
| DeepSeek-OCR 2 | panel OCR cross-check | pinned source commit and HF model revision |

Install or inspect one tool:

```bash
mediaconductor install-tool index-tts
mediaconductor tools --json
mediaconductor doctor --mode manga-video --json
```

All HF, Torch, uv Python, Triton, TorchInductor, NLTK, and extension caches are
redirected below `runtime/cache/`, so a model is downloaded once per install
and never scattered into a global cache. Set `MEDIACONDUCTOR_SHARE_CACHES=1`
only when deliberately opting into global caches, and `MEDIACONDUCTOR_HOME` to
point several checkouts at one shared `runtime/` tree.

## Safety and publishing

- Upload requires a current, hash-bound `manga-review final-video` record for
  the exact file, which in turn requires current crop and narration reviews.
- Upload requires a complete `manga-rights` manifest: source URL, edition,
  language, creator, publisher, permission basis, allowed chapters,
  attribution, translation provenance, voice consent, music licences,
  thumbnail source panels, and clear nudity / sexualized-minors / graphic-gore /
  misleading-thumbnail scans. Unknown ownership blocks publication.
- Default upload privacy stays `private`. Replacement is upload-new → verify →
  delete-old.
- `publish.json` prevents accidental repeat uploads.
- Destructive cleanup requires an allowed generated root and exact
  directory-name confirmation, and never touches `data/library/`.
- MCP path arguments and typed background jobs are confined to the server's
  repeatable `--allow-root` workspace boundary.
- Project item and claim identifiers reject path traversal.
- OAuth JSON is atomically written with owner-only file permissions where the
  platform supports them. Tokens are never printed.
- Multiple named YouTube profiles can isolate channels. Discover them with
  `mediaconductor youtube-profiles --json`. A live status/upload opens browser
  consent automatically when needed; `--no-auto-auth` disables that for
  headless use.
- MediaConductor ships no manga, music, or voice samples. Supply only media you
  are licensed and authorized to use.

YouTube OAuth requires a one-time browser action by the channel owner. Follow
[docs/youtube.md](docs/youtube.md). API projects that have not passed Google's
audit can have uploads forced to private regardless of the requested setting.

Relevant platform policy: [fair
use](https://support.google.com/youtube/answer/9783148?hl=en),
[reused/inauthentic
content](https://support.google.com/youtube/answer/1311392?hl=en-EN),
[thumbnails](https://support.google.com/youtube/answer/9229980?hl=en),
[synthetic-content
disclosure](https://support.google.com/youtube/answer/14328491).

## Machine contract

- `0`: success.
- `1`: runtime/validation failure.
- `2`: invalid CLI usage.
- `3`: artifact created, but human/agent QA approval is required.
- `--json` commands print one JSON report.
- Generation commands finish with `MEDIACONDUCTOR_RESULT {...}` for 2.x
  compatibility.
- Progress lines use `MEDIACONDUCTOR_PROGRESS current/total label`.

Use `mediaconductor commands --mode manga-video --json --full` instead of
scraping help text.

## Development and production checks

```bash
uv sync
uv run ruff check .
uv run python -m compileall -q mediaconductor
uv run pytest
```
