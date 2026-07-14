# Repository reorganization plan — make mangaEasy self-explanatory to any LLM

Status: **active** · Started 2026-07-09 · Owner: reorg effort

> This is a historical planning + tracking doc. The living documentation it
> produced lives in `docs/`, `CLAUDE.md`, `AGENTS.md`, and per-package
> `README.md` files. (2026-07-14: `START_HERE.md` was retired — its doc map
> and code map were folded into `CLAUDE.md`, its agent quickstart into
> `AGENTS.md`.) This file stays as the record of *why* the structure is what
> it is.

## Goal

An AI agent (or human) opens `D:\mangaEasy` cold and can both **operate** the
pipeline and **modify** the code without guessing — because every directory
documents itself, the two command eras stop overlapping, and CI fails the
moment docs drift from code. The **crop → verify → see → narrate** loop is
built first, as the flagship worked example the whole doc system is modeled on.

## Decisions (locked with the owner)

| Question | Decision |
|---|---|
| How far to change the repo | **Full reorganization** — move/rename modules + docs, unify the two command eras |
| Pain points to fix | Legacy-vs-new code, overlapping docs, no "start here" map, uncommitted scratch scripts (all four) |
| Primary reader | **Coding agent** modifying/extending the codebase |
| Keep it fresh | **Automated checks in CI** — fail the build on doc drift |
| Fate of legacy chapter commands | **Hard-remove** (see the desktop caveat below — confirmed at Phase 1 boundary) |
| Review cadence | **Full autonomy**, report at each phase boundary |

## The mess, precisely

1. **Two eras of commands coexist with no boundary.**
   - *New (keep):* item pipeline `video-*` → `mangaeasy/video_pipeline/`.
   - *Legacy (remove):* chapter commands `render-video`, `add-bgm`,
     `join-chapters(-nobgm)`, `timestamps`, `fade-audio`,
     `normalize-chapter-audio`, `process-panels`, the `narration-editor*` /
     `narration-review` / `cut-page` / `panel-editor` Flask editors, and the
     `init/increment/reset/fix-name/clean` chapter-bookkeeping commands.
2. **Five overlapping top-level guides** — `CLAUDE.md`, `AGENTS.md`,
   `docs/ai-guide.md`, `docs/recap-video-playbook.md`, `README.md` — plus three
   stale historical plans (`docs/ai-cli-plan.md`, `docs/production-plan.md`,
   `docs/youtube-upload-plan.md`).
3. **No "start here" map** at the repo root.
4. **The page crop path is uncommitted scratch scripts** pasted inside
   `docs/recap-video-playbook.md` (Phases 2–3), while the webtoon path is a
   clean one-command tool (`webtoon-split`) with verification built in.

## Target documentation architecture (coding-agent-first)

Strict hierarchy; one authoritative home per fact, everything else links.

| File | Role |
|---|---|
| `START_HERE.md` (root) | Single entry map: what this is, layout, which doc for which job, golden-path commands. |
| `CLAUDE.md` | Dev conventions & invariants only (the "don't break this" list). |
| `docs/architecture.md` | Subsystem map: pipeline diagram, each stage → its package → its README. |
| `docs/operate/` | Operator playbooks (`recap-video-playbook.md`, `crop-verify-narrate.md`). |
| `docs/reference/` | CLI reference (checked against `COMMANDS`), config schema, data-layout spec. |
| `mangaeasy/<pkg>/README.md` | One README per package: what it does, entry points, callers, gotchas. |
| `AGENTS.md` | Thin pointer to `START_HERE.md`. |
| `docs/history/` | Stale plans archived here + this file. |

## Target code structure (unify the eras, by pipeline stage)

```
mangaeasy/
  core/        cli, config, defaults, paths, runtime, library_scan, mcp_server
  acquire/     download/ + panels/  (page + webtoon crop, clearly separated)
  narrate/     narration/ helpers + the narration prompt/spec
  produce/     the item pipeline (today's video_pipeline/) — the ONE render path
  publish/     youtube/
  tools/       external tool envs (unchanged)
  images/      shared image ops (ai_zip, convert, pdf, watermark)
  web/         Flask editors (only those kept)
```

Exact package names to be finalized in Phase 2; the invariant is
*organized by the pipeline stage a reader already learned from START_HERE*.

## Flagship (built first): crop → verify → narrate

1. **`mangaeasy page-split`** — a real command mirroring `webtoon-split`: MAGI
   v3 batch-detect (model loaded once) → reading-order crop → auto contact
   sheet + overlay verification images → `MANGAEASY_RESULT`. Retires the
   copy-paste scripts in the playbook.
2. **`docs/operate/crop-verify-narrate.md`** — one self-contained doc: decide
   webtoon vs page → crop → clear every verification flag → read the chapter →
   write `narration.json`, with `assets/prompts/narration.md` as the spec.
3. This doc is the **template** every other operator doc + package README
   matches.

## CI enforcement (extends tests/test_docs_crossref.py)

- Every `COMMANDS` entry appears in the CLI reference and vice-versa.
- Every package dir under `mangaeasy/` has a `README.md`.
- Every internal markdown link and `file:line` code reference resolves.
- `START_HERE.md` names every top-level package (new package → CI fails until
  documented).

## Phases (each ends green: `uv run pytest` + `ruff check` + desktop build)

- **Phase 0** — Save this plan + the legacy/new inventory. *(no behavior change)* ✅ this file
- **Phase 1** — Docs only, no code moves: `START_HERE.md`, per-package READMEs,
  trim `CLAUDE.md`, archive stale plans, add doc-integrity CI, **ship
  `page-split` + the flagship doc.**
- **Phase 1 boundary report** — surface the desktop Workflow/Editor decision
  (see inventory) before any legacy removal.
- **Phase 2** — Stage-based package reorg; remove legacy Python + migrate/remove
  the dependent desktop tabs. Contract tests stay green.
- **Phase 3** — Turn on the full CI gate, regenerate the CLI reference, final
  cold-read pass.

See `docs/history/legacy-inventory.md` for the per-module removal/keep table
and the desktop dependency map.
