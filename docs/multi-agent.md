# Multi-agent production — coordination, resume, QA loops, reuse

mangaEasy assumes any number of agents (or one agent across many interrupted
sessions) may work the same project. That "one agent across interrupted
sessions" case explicitly includes **switching which LLM is driving** —
Claude runs out of budget mid-batch, and GPT (or any other model) picks the
exact same project back up. Nothing in the workboard is Claude-specific or
tied to one chat session: it's plain JSON/JSONL under
`data/library/<Project>/.workboard/`, so it travels with the project, works over a
network share, and item scanning ignores it. The filesystem stays the single
source of truth for *work done*; the workboard coordinates *work in
progress* and *working memory* — the facts and plans that would otherwise
live only in one model's context window. See
[Switching LLM providers mid-project](#switching-llm-providers-mid-project)
below for the handoff recipe.

---

## Story Memory: MEMORY.json

`data/library/<Project>/MEMORY.json` is the project's **external episodic
memory**. It exists because:

- Context windows are finite. A 12-chapter batch can easily exceed 100K tokens
  of narration text — loading all of it burns budget, hits limits, and still
  loses everything at session end.
- Sessions end unexpectedly (budget, context, crashes). When they do, anything
  only in the model's working memory is gone.
- LLM providers change mid-project. The next model has no shared memory with
  the last one.

The solution — consistent with MemGPT (Packer et al., 2023) and Anthropic's
external memory guidance — is **hierarchical disk-based memory** where the
model reads the compact working set (`brief`), loads detail sections on demand,
and writes new facts to disk the moment they are established.

### Schema

```jsonc
{
  "version": 2,
  "project": "solo_leveling",              // Mandatory project isolation anchor
  "updated_at": "2026-08-05T10:00:00Z",   // ISO-8601, set on every write
  "updated_by": "claude-fable",            // MANGAEASY_AGENT value

  // ── HOT: read first, every session ───────────────────────────────────────
  "brief": [
    // ≤ 40 lines. THE ENTIRE COLD-START WORKING SET.
    // Each line: "<topic>: <one compact sentence>"
    // A fresh agent reads only this and can act on the project.
    // When this block grows past 40 lines, trim it (see protocol below).
    "premise: Low-ranked hunter silently absorbs the powers of everything he defeats.",
    "cast: Ren (M, protagonist, silver hair, E-rank → rising, conf:high), Labyris (F, red-haired knight, tsundere, conf:high), unnamed dragon (conf:low — name not yet revealed as of ch06)",
    "tone: Dark isekai, dry humor, occasional betrayal twist.",
    "style: high-engagement YouTube recap; casual persona (\"our boy\", \"bro\").",
    "batch: 01-12 in progress. ch07 audio pending.",
    "overrides: ch03 page5 is a montage — overrides.json must always be passed to page-split."
  ],

  // ── WARM: load only the section you need ─────────────────────────────────
  "characters": {
    // One entry per named character. Load only the entry you need, not the whole object.
    // conf: "high" | "medium" | "low"
    // NEVER state a conf:low name as established in narration.
    "Ren": {
      "role": "protagonist",
      "appearance": "silver hair, one-star badge on introduction page",
      "speech_style": "quiet, direct; rarely expresses surprise aloud",
      "introduced": "01_001_01.jpg",
      "aliases": [],
      "conf": "high"
    }
  },

  "beats": {
    // Per-chapter plot beats tied to panel IDs.
    // Load beats["N"] ONLY when narrating chapter N. Do NOT load all chapters.
    "01": [
      {"panel": "01_003_02.jpg", "beat": "Ren announced as E-rank in the guild assessment.", "conf": "high"},
      {"panel": "01_015_01.jpg", "beat": "First absorption: Ren silently takes the goblin's speed.", "conf": "high"}
    ]
  },

  // ── COLD: load on demand, not routinely ──────────────────────────────────
  "decisions": [
    // Crop, narration, and tone decisions with reasoning.
    // Load a decision only when revisiting that chapter or panel.
    {
      "ts": "2026-08-05T08:00:00Z",
      "agent": "claude-fable",
      "topic": "crop",
      "decision": "ch03 page5 is a montage — explicit boxes in overrides.json.",
      "reason": "MAGI returned automatic-full-page-box; visual inspection confirmed 4 bordered panels hidden by black fill."
    }
  ],

  "open_questions": [
    // Unresolved facts. Use conf:low. Remove an entry when resolved.
    {"id": "q1", "question": "Dragon name — not revealed on page as of ch06.", "conf": "low"}
  ]
}
```

### Memory Protocol (NON-NEGOTIABLE)

#### READ — hierarchical, never load the full story

| What you need | What to read | What NOT to do |
|---|---|---|
| Starting a session | `brief` only (≤40 lines) | Do not open all `narration.json` files |
| Narrating chapter N | `beats["N"]` | Do not load all other chapters' beats |
| Recalling a character | `characters["Name"]` | Do not re-read prior chapters |
| Revisiting a decision | `decisions` filtered by chapter | Do not re-derive from scratch |

`conf: low` facts are hypotheses. **Never state them as established in narration or decisions.**

#### WRITE — immediately on learn, not batched at session end

Every new fact goes to disk **before you continue**. A cut-off session loses anything you only intended to write later.

| What you established | Write immediately |
|---|---|
| New character name, appearance, speech style | `work-note --topic characters` **+** append entry to `MEMORY.characters` |
| New power, title, relationship, reveal | `work-note --topic story` **+** append beat to `MEMORY.beats[chN]` |
| Crop or narration decision with reasoning | Append to `MEMORY.decisions` |
| Unresolved name, unclear speaker, ambiguous panel | Append to `MEMORY.open_questions` with `conf: low` |
| A `conf: low` fact confirmed on-panel | Remove from `open_questions`, move to `characters`/`beats` as `conf: high` |

Write `MEMORY.json` as a complete file each time (read → update in memory → write back). Keep `updated_at` and `updated_by` current on every write.

#### TRIM — when `brief` exceeds 40 lines

1. Compress finished chapters to one line per range: `"ch01-03: Ren rises from E-rank to C-rank; meets Labyris."`.
2. Move character detail to `characters`; keep only `name + role + conf` in `brief`.
3. Keep only the current batch window active in `brief`; push older windows to `beats`.
4. After trimming, write the file and confirm `brief` ≤ 40 lines.

#### SESSION END — mandatory before stopping or handing off

```bash
# 1. Write updated MEMORY.json (trim brief, flush new facts, update updated_at + updated_by)
# 2. Leave a handoff note — the narrative, not just the stage:
mangaeasy work-note --project-root data/library/<P> --topic handoff \
    --add "item 07 video-render was running in the background; verify job-status before re-launching. \
           Next: ch08 narration (reading sheet shows dense text panel 08_012_03 — OCR optional)."
# 3. Leave next steps that aren't visible on disk:
mangaeasy work-todo --project-root data/library/<P> \
    --add "Redo ch10 thumbnail — user wants split-preset variant" --topic publishing
```

**The next agent — any model, any vendor — reads `MEMORY.json` (step 0b) and picks up exactly where you left off, without re-reading the entire story.**

---



## The session protocol

Every session — first or fiftieth, alone or with other agents (or other
models) running — starts the same way:

```bash
mangaeasy work-status --project-root data/library/<Project> --json   # where is everything?
mangaeasy work-status --project-root data/library/<Project> --next   # what should I grab?
```

`work-status` derives each item's stage (`download → crop → narrate →
audio → render`, with `transcribe` surfacing only when a panel-transcript
run was started and left unfinished — OCR itself is optional) purely from
files on disk, so it is correct even if the previous agent died mid-run. It
also shows live claims, the latest shared notes, and open todos (below) in
one report — that combination is the full resume briefing a fresh agent
needs, regardless of what wrote the code that produced it. `--next` lists
only the unclaimed, actionable tasks.

Then loop. `work-status --next --json` includes deterministic command
suggestions for the small mechanical stages; use them instead of reconstructing
basic invocations in the prompt.

1. **Claim** the task before touching it:
   `mangaeasy work-claim --project-root data/library/<P> --item 07 --stage narrate --agent me`
   Exit 0 = yours (lease default 60 min); exit 1 = someone live holds it —
   pick another task. Long job still running? `--renew`. Done? `--release`.
   Expired leases are taken over automatically, so a crashed (or simply
   cut-off) agent never wedges the board.
2. **Hold the GPU mutex around GPU model work.** `page-split`,
   `panel-transcript`, and TTS (`video` / `video-audio-indextts`) each load
   a multi-GB model — two at once on a consumer card is an OOM:
   `mangaeasy work-claim --project-root data/library/<P> --resource gpu --agent me`
   (release it the moment the GPU step exits; NVENC rendering does not need
   it). Give it a `--ttl-minutes` that covers the whole job.
   Start long commands with `job-start`, then stop actively polling until the
   expected work window has passed. `job-status` is the wake-up point; if it is
   still running, renew/recheck later rather than keeping an LLM loop alive.
3. **Write down what the next agent needs.** Character names, speaker
   conventions, tone decisions, warnings — the facts that otherwise die with
   your context window:
   `mangaeasy work-note --project-root data/library/<P> --add "Labyris = red-haired knight, tsundere, calls Chrome 'onii-chan'" --topic characters`
   Read the notebook before narrating anything: `mangaeasy work-note --project-root data/library/<P> --list`.
   Narration written by different agents must agree on names and voice — the
   notebook is how.
4. **Track plan-level next steps on the shared todo list** — see
   [Session todo list](#session-todo-list) below.
5. **Verify with the QA loop** (below), release your claims, repeat from
   `work-status --next`.

## Session todo list

`work-status` and `work-claim`/`work-note` cover everything derivable from
the filesystem or worth writing down as a fact. But a production run also
carries **plan-level intent** that lives in neither place: "this batch stops
at chapter 24", "the user asked for the ch10 thumbnail redone", "confirm the
tone on that reveal panel before uploading". `work-todo` is a small, ordered,
shared checklist for exactly that — the same working-memory role a coding
agent's own in-session todo list plays, except it's a file next to the
project instead of state inside one process, so it outlives any single
context window or model:

```bash
mangaeasy work-todo --project-root data/library/<P> --add "Redo ch10 thumbnail text" --topic publishing
mangaeasy work-todo --project-root data/library/<P> --list
mangaeasy work-todo --project-root data/library/<P> --start 3   # mark in_progress
mangaeasy work-todo --project-root data/library/<P> --done 3    # mark done
mangaeasy work-todo --project-root data/library/<P> --reopen 3  # undo a premature "done"
mangaeasy work-todo --project-root data/library/<P> --remove 3  # no longer relevant — delete it
```

Open (non-done) todos also appear directly in `work-status`'s report (capped
at 10, with a count of how many more exist), so reading the resume briefing
once surfaces them without a separate call. Storage is an append-only event
log (`todo.jsonl`, same durability model as `notes.jsonl`) — ids are assigned
once and never reused, even after `--remove`, so an id mentioned earlier in
a conversation or a note always means the same todo.

## Switching LLM providers mid-project

The scenario this is built for: you're mid-batch, the current model runs out
of budget or context, and a different one (different vendor, different
session, no shared memory of the conversation) needs to continue as if it
were the same worker. Nothing here is special-cased per model — it's the
ordinary multi-agent protocol above, applied across a vendor boundary
instead of across two processes:

1. **Identify the model in claims/notes/todos** by setting
   `MANGAEASY_AGENT` before it runs (e.g. `export
   MANGAEASY_AGENT=claude-fable` vs. `gpt-5.6`). Every claim, note, and
   todo records who touched it, so a later agent can tell which decisions
   came from which model — useful when judging whether to trust a stylistic
   call (e.g. a narration tone choice) without re-deriving it.
2. **Before a session ends — planned or forced —** leave a `handoff`-topic
   note describing exactly what was in flight, not just what stage you were
   on: `mangaeasy work-note --project-root data/library/<P> --topic handoff
   --add "item 14 video-render was running in the background when I was cut
   off; check job-status before re-launching, don't assume it crashed."`
   Filesystem state plus a claim lease already recover *what stage* an item
   is at; the handoff note recovers the *narrative* — the one thing an
   interrupted session can't reconstruct from disk alone. Add any
   not-yet-actioned next step to `work-todo` too.
3. **A session that starts cold** — any model, any vendor — runs exactly the
   step 0 orientation from the top of this doc:
   `work-status --json` (stage + claims + notes + todos in one report), then
   `work-note --list --topic handoff` for the full text of the last
   handoff note (the summary in `work-status` is capped), then proceeds from
   `work-status --next`. There is no prompt or config to port between
   models — the same three commands work whether the previous agent was
   itself, or something else entirely.
4. **Claims outlive the process that took them** (TTL lease, not a
   heartbeat), so a session that vanished mid-GPU-job doesn't need to be
   "informed" that it's gone — the lease simply expires and the next agent's
   `work-claim` takes over automatically. Set `--ttl-minutes` generously for
   long GPU jobs so a slow model download doesn't get pre-empted by an
   impatient takeover.

Claims are advisory by default. When you want them *enforced*, the heavy
commands (`video`, `page-split`, `webtoon-split`, `panel-transcript`) accept
`--respect-claims [--agent me]`: they abort with exit 1 — naming the holder —
if another live agent's claim covers any selected item at that stage.

Project-level stages (`join`, `thumbnail`, `upload`) are single-agent by
nature — claim them without `--item`:
`mangaeasy work-claim --project-root data/library/<P> --stage join --agent me`.

## The fix-until-clean QA loop (built for small models)

`mangaeasy work-qa` aggregates every machine-checkable gate over the
generated artifacts — crops exist, OCR coverage, narration structure
(dangling images, empty text, intro/narration overlap), speakability and
delivery/fluency lint, audio coverage + integrity, render freshness — into
one ordered problem list. **Every problem carries the exact fix command.** A
small model needs no global judgment; the whole correction workflow is:

```bash
until mangaeasy work-qa --project-root data/library/<P> --items 07 --errors-only --json; do
    # read problems[0].fix, run/apply it, repeat
done
```

- Exit 0 and `ok: true` mean machine-clean only; exit 1 means machine errors
  remain. Problems come in pipeline order, so fixing the first one is safe.
  Always inspect `manual_review_required` separately before production.
- `--max-problems` (default 25) keeps the list inside a small context
  window; fix, re-run, the next slice appears.
- `severity: "review"` items are the checks that need **eyes** (source-page
  overlays, full-resolution crops, and narration review sheets). They do not
  change the machine-loop exit code. A vision-capable reviewer inspects
  flagged/suspect artifacts first, samples clean outputs, and broadens if
  errors appear; detector confidence, OCR agreement, contact sheets, or another
  retry cannot approve them. Semantic narration QA (right speaker, one beat per
  panel) stays a vision-pass job:
  `mangaeasy narration-review-sheets`, then read every sheet and original.
- `severity: "info"` = normal-but-worth-confirming (e.g. uncovered
  credits/banner panels).

## Reuse before regenerate

Everything expensive is archived, never clobbered (`old/run_NNNN/`,
timestamped long videos, hash-cached music beds). Before regenerating
anything, check the inventory:

```bash
mangaeasy work-artifacts --project-root data/library/<P> --json
```

Each category comes with its reuse hint — the important ones:

- **item renders** are reused as-is by `video-join`; `mangaeasy video
  --skip-audio` re-renders only stale items.
- **TTS audio** is reused by any rerun without `--overwrite-audio`;
  overwritten takes are archived — `mangaeasy audio-takes-list` /
  `mangaeasy audio-takes-restore` bring an old take back without
  regenerating.
- **transcripts** (`<item>/transcript.json`) are optional, untrusted OCR
  cross-evidence. Reuse a row only while its `panel_sha256` still matches the
  current crop; consumers suppress stale or legacy-unbound OCR automatically.
- **music beds** are cached by content hash; `mangaeasy video-add-bgm`
  reuses them automatically.

## MCP

All six commands are exposed as MCP tools (`work_status`, `work_claim`,
`work_note`, `work_todo`, `work_qa`, `work_artifacts`) by `mangaeasy mcp`,
so agent hosts get the same coordination surface as the CLI — including a
host running a different model than the one that last touched the project.
