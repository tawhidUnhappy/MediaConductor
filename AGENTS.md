# Agent notes for mangaEasy

**Using the tool** (turning images + narration into videos): the entire tool
surface is the `mangaeasy` CLI — read **[docs/ai-guide.md](docs/ai-guide.md)**
first; it is the complete operating manual (install modes, data anatomy,
recipes, JSON/exit-code contract, safety rules). Orient with:

```bash
mangaeasy where --json             # this install's data/tool paths + version
mangaeasy commands --json --full   # full catalog WITH argument schemas — no per-command --help needed
mangaeasy doctor --json            # machine readiness (ffmpeg, GPU, AI tools)
```

No command prompts for input. `--json` commands print one JSON object;
generation commands end with a `MANGAEASY_RESULT {"outputs": [...]}` line.
An MCP server is available: `mangaeasy mcp` (stdio) — same engine, typed tools.

**Long-running steps** (download, page-split, panel-transcript, video, zimage,
youtube-upload — minutes to hours each; `commands --json --full` marks them
`long_running`): never block on them. Either use your harness's background
shell, or the built-in job runner from any environment:

```bash
mangaeasy job-start video --project-root library/<P> --item-range 01-12 ...
mangaeasy job-status <job-id> --json    # running/succeeded/failed/orphaned + progress + result
mangaeasy jobs --json                   # everything, newest first
```

Fresh clone or fresh machine? Follow the runbook in [docs/setup.md](docs/setup.md):
`uv sync` → `mangaeasy setup` → `mangaeasy doctor --json` → `mangaeasy
smoke-test` (renders and verifies a tiny real video — proof the env works).

**Several agents on one project / resuming after interruption**: follow
[docs/multi-agent.md](docs/multi-agent.md) — `work-status` (resume), `work-claim`
(don't collide), `work-note` (share story facts), `work-qa` (fix-until-clean loop),
`work-artifacts` (reuse instead of regenerate).

**Producing a recap series** (MangaDex URL → uploaded videos, 12 chapters per
video): follow the skill at
[.claude/skills/manga-recap/SKILL.md](.claude/skills/manga-recap/SKILL.md) —
Claude Code loads it automatically; other agents can read it as a runbook.

Hard safety rules: never delete/rename inside `library/` source items; clear
generated output only via the `video-clean-*` commands (everything else is
archived to `old/run_NNNN/`, never silently destroyed); edit narration through
`narration-edit`, not by hand. Unsafe values are clamped in code
(`--gpu-workers` caps at 4), so out-of-range requests warn instead of crashing
the GPU.

**Developing this repo** (changing mangaEasy itself): read
[CLAUDE.md](CLAUDE.md) — doc map, code map, architecture, invariants,
test/lint requirements (`uv run pytest`, `uv run ruff check .`).
