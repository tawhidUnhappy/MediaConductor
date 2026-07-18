# Local LLM (Gemma 4) — assist commands for small driver agents

MediaConductor's manga workflow was designed for a strong multimodal agent:
it must pick the right splitter, *look at* crop verify sheets, write grounded
narration with correct speaker names, and review its own output. In real
production runs, smaller or text-only driver agents (or agents driven from
chat UIs without vision) skipped exactly those steps — wrong splitter on a
webtoon, unreviewed forced cuts shipped into narration, invented character
names.

The assist layer moves that vision-and-judgement work into the toolkit
itself, running Google's **Gemma 4 E4B** (Apache-2.0, text + image input)
locally in an isolated tool env. The driver agent — of any size — only has to
run commands and read exit codes.

```bash
mediaconductor install-tool gemma-4     # ~6 GB; CPU-capable, GPU via Vulkan
```

## The one-command path

```bash
mediaconductor manga-auto --url "<MangaDex title URL>" --name example
# ... runs: download → style-detect → the CORRECT splitter → crop-qa →
#           panel-transcript → characters --auto-draft → narrate-auto
# exits 3 with a review checklist (sheets + reports + characters.json)

# after reviewing/fixing:
mediaconductor manga-auto --project-root library/example --stage build
# ... runs: video (TTS + render + join + normalize) → video-validate → work-qa
```

Every stage is the ordinary CLI command in a subprocess — identical logs and
artifacts, resumable by re-running. `manga-auto` never publishes; thumbnails,
music, and YouTube remain explicit separate steps (see the manga-video skill).

**Exit code 3 always means "artifacts ready — review them".** It is not an
error, and it is not permission to skip the review.

## The building blocks

### `crop-qa` — automated crop review

```bash
mediaconductor crop-qa --project-root library/example --items 01 --work-dir work
```

For webtoon items it renders a full-resolution window around every forced
auto-split cut and short panel from the `webtoon-split` ranges manifest (same
geometry as `webtoon-cutcheck`) and asks Gemma per window: *does this cut
slice a figure or speech bubble?* For paged items it reviews every `page-split`
overlay for missed/merged/misordered boxes.

Every FIX verdict is printed with the exact fix command
(`webtoon-override --merge-at-cut ...` / a `page-split --overrides` entry) and
recorded in `work/crop_qa/<project>/<item>_report.json`. Exit 3 = apply the
fixes, re-split, re-run until exit 0. Unreadable model replies are counted as
`unreviewed` and also force exit 3 — nothing silently passes QA.

The model is a reviewer, not an oracle: spot-check FIX verdicts on the
referenced window images before large re-crops.

### `characters` — the cast registry

```bash
mediaconductor characters --project-root library/example --auto-draft
mediaconductor characters --project-root library/example          # validate/show
```

`<project-root>/characters.json` holds canonical names, aliases, appearance
cues, and roles. `--auto-draft` samples panels across the series and drafts it
with Gemma (names only when attested by OCR/on-panel text, descriptive handles
otherwise). Drafts are always written with `"draft": true` — review the names
against the story, then set `draft: false`. `narrate-auto` injects the
registry into every prompt so speaker attribution stays consistent across
chapters; hand-written narration should use it the same way.

### `narrate-auto` — grounded narration drafts

```bash
mediaconductor narrate-auto --project-root library/example --items 01
```

Chunk by chunk (default 8 panels per vision request) it feeds Gemma the panel
images, their `transcript.json` OCR, the character registry, and a running
story-so-far summary; banner/credit panels are skipped, and panels the model
can't handle are left for manual narration (warned, never invented). It then
runs `narration-check` and renders `narration-review-sheets`, and exits 3:
**read every review sheet** and fix wrong speakers/claims with
`narration-edit` before TTS — the same gate human-written narration goes
through. Existing `narration.json` files are never overwritten without
`--overwrite`.

### `llm` — raw access

```bash
mediaconductor llm --prompt "Who is in this panel?" --image panels/ch01_004.jpg
mediaconductor llm --batch-manifest requests.json     # one model load, many requests
```

Text + images in, text (optionally JSON-schema-constrained) out. Useful for
custom checks; the assist commands are built on the same call path
(`tools/gemma.py:batch_generate`).

## Guardrails that back all of this up

These run regardless of whether Gemma is installed:

- **Style guard** — `webtoon-split` refuses pages that measure as paged manga
  and `page-split` refuses vertical strips, each naming the correct command
  (override with `--force-style` for genuinely mixed items). Running the wrong
  splitter was the most expensive small-agent failure we saw.
- **Workspace resolution** — `setup` registers the workspace; commands started
  from a wrong cwd resolve the registered workspace instead of silently
  creating a second `library/` tree. `download` prints its destination before
  any network work, and `where --json` reports `workspace_root`.

## The local endpoint: `llm --serve`

The gemma-4 install doubles as a **free local OpenAI-compatible server** —
the same weights and GPU runtime the pipeline uses, no second download, no
API key, no cloud:

```bash
mediaconductor llm --serve            # http://127.0.0.1:8080/v1  (Ctrl+C stops)
mediaconductor llm --serve --port 9090
```

Vision is enabled (clients can send images), thinking is disabled by default
(`--reasoning-budget 0`) so replies never come back empty, and any non-empty
string works as the API key. Every OpenAI-compatible client can use it:
Cline, Roo Code, Continue, LM Studio's chat, Open WebUI, curl.

Want Gemma's full thinking mode for agent/chat use?

```bash
mediaconductor llm --serve --reasoning-budget -1
```

The server separates deliberation into the response's `reasoning_content`
field, so clients like Cline render it as a collapsible "Thinking" block
while the final answer stays clean (verified). Thinking improves multi-step
agent reliability at the cost of slower replies; the pipeline's own assist
commands always run with thinking off regardless of the serve flag.

## Driving MediaConductor from VS Code with Cline (local + free)

[Cline](https://github.com/cline/cline) is an open-source agent extension —
it runs terminal commands and speaks MCP, like the Claude Code/Codex panels,
but works with any model endpoint. Paired with `llm --serve`, the whole
stack is local and free.

**1. Install the extension** (either way):

```bash
code --install-extension saoudrizwan.claude-dev
```

or Extensions view (`Ctrl+Shift+X`) → search "Cline" → Install.
(Alternatives with the same setup shape: Roo Code
`RooVeterinaryInc.roo-cline`, Continue `Continue.continue`.)

**2. Put it next to Claude Code / Codex**: Cline appears as an icon in the
left Activity Bar. Drag that icon into the right-hand Secondary Side Bar
(or right-click the icon → *Move To* → *Secondary Side Bar*). It docks as
another tab beside the other agent panels.

**3. Start the local model** (keep this terminal open, or run it as a
background job):

```bash
mediaconductor llm --serve
```

**4. Connect Cline to it**: open the Cline tab → gear icon (Settings) →
API Configuration:

| Setting | Value |
|---|---|
| API Provider | **OpenAI Compatible** |
| Base URL | `http://127.0.0.1:8080/v1` |
| API Key | anything non-empty, e.g. `local` |
| Model ID | `gemma-4` |
| Supports images | enabled (the endpoint serves vision) |

**5. Give it the MediaConductor tools (MCP)**: Cline tab → MCP Servers icon
→ *Configure MCP Servers*, and add:

```json
{
  "mcpServers": {
    "media-conductor-manga": {
      "command": "uv",
      "args": ["--project", "D:/MediaConductor", "run", "mediaconductor",
               "mcp", "--mode", "manga-video",
               "--allow-root", "D:/MediaConductor"],
      "disabled": false
    }
  }
}
```

(For a global/wheel install, `"command": "mediaconductor"` with just the
`mcp ...` args works; a source checkout can also point `command` straight at
`<checkout>\.venv\Scripts\mediaconductor.exe`. Adjust the workspace path to
yours. The same JSON can be written directly to Cline's settings file at
`%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`;
add read-only tools such as `work_status`, `job_status`, `library_list`,
`style_detect`, `narration_check`, `work_qa` to `"autoApprove"` so status
polling doesn't require a click per call.)

**6. Drive it.** A good first message to the Cline agent:

> Run `mediaconductor manga-auto --url "<MangaDex URL>" --name <project>`
> as a background job, watch job-status, and stop at any exit-3 gate to
> show me the review checklist.

Expectation management: a 4B-effective local model is a capable *operator*
of these rails (run commands, read exit codes, relay checklists) but not a
strong *reviewer* — the exit-3 gates and your own eyes stay in the loop.
Other workable drivers: Roo Code / Continue (same endpoint settings), or
any MCP-capable chat UI (LM Studio ≥ 0.3.17, Open WebUI with an MCP
bridge) pointed at the same `--serve` URL.

Whatever the driver, keep it on the rails: `commands --mode manga-video --json
--full` for discovery, background jobs for anything long-running, and treat
exit 3 as "look at the listed artifacts before continuing".
