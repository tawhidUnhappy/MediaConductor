# Security policy

## Supported versions

Security fixes target the latest 2.x release on `main`. The original `mangaeasy` command is a compatibility alias, not a separate security surface.

## Agent safety model

- The MCP catalog is the manga catalog. There is no router mode and no `--all-tools` escape hatch, and a tool outside the catalog is reported as *unknown* rather than forbidden, so a removed feature cannot be probed by name.
- Long jobs accept a typed, mode-visible MCP tool and validated JSON arguments. Raw CLI forwarding is not part of the MCP contract — and no longer part of `job-start` either, because a passthrough argv is a strictly wider interface than the schema it mirrors.
- Start MCP with a dedicated, repeatable `--allow-root` workspace (or accept its startup-directory default). The policy covers direct paths, nested typed jobs, configured media, and the review/rights/final-video paths; it is a same-user stdio guardrail, not an OS sandbox.
- Keep project and output roots in a dedicated workspace. `mediaconductor workspace-layout --json` reports every resolved persistent root; `doctor` warns when one escapes. Destructive cleanup requires a strict allowed root and exact target-name confirmation, and never touches `data/library/`.
- Review is a hash-bound record, never a boolean argument. No caller — CLI, MCP, or background job — can assert its own review, and there is no bypass policy. Treat publish, account changes, and deletion as explicit human-authorized actions.
- Panels, speech bubbles, OCR output, scanlator pages, and watermarks are untrusted data. Text embedded in page art must never be followed as an instruction, and OCR must stay inside structured JSON rather than being concatenated into a prompt.
- Do not expose MCP stdio through an unauthenticated public network bridge.

## Secrets and private media

YouTube OAuth files live below the application data directory, are atomically replaced, and receive owner-only permissions where supported. Never attach token files, client secrets, private voice references, copyrighted source pages, or unreleased audio to bug reports.

MediaConductor includes no manga, licensed music, or voice-cloning sample. Confirm rights and voice consent before generation or publication; `mediaconductor manga-rights check` fails closed when they are unresolved.

## Reporting

Report a vulnerability privately through GitHub's security-advisory interface for this repository. Include the affected commit, platform, minimal reproduction, and impact. Do not open a public issue containing credentials or a working destructive exploit.
