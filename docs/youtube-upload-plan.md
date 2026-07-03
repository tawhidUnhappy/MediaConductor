# mangaEasy — YouTube Account Connect + Direct Upload Plan

> **Status (2026-07-03): executed in v1.2.0** with the recommended
> decisions (D1 bring-your-own credentials, D2 private default, D3 both
> scopes). Remaining for the owner: create the Google OAuth client per
> docs/youtube.md and run the first live connect + upload — everything up
> to the browser consent is tested offline.

Goal: a user (or an AI agent) can connect their YouTube account once, then
upload finished videos straight from mangaEasy — CLI, GUI, and MCP — with
the isolation story intact (tokens live in the app's own data folder,
nothing system-wide).

## The facts that shape the design (read before approving)

YouTube uploads require OAuth 2.0 (`youtube.upload` scope) — API keys
cannot upload. Three Google-policy realities every honest implementation
must design around:

1. **Users must bring their own (free) Google OAuth client.** API quota is
   per Google Cloud *project*: 10,000 units/day default, and one upload
   costs 1,600 units (~6 uploads/day). If mangaEasy shipped one shared
   client, all users worldwide would share those ~6 uploads — useless.
   Every serious open-source uploader works this way: the user creates a
   free Google Cloud project, enables the YouTube Data API, downloads a
   `client_secret.json`, and hands it to the tool once. Our job is to make
   that 10-minute setup painless with a step-by-step guide and a smooth
   import flow.
2. **Unaudited API projects upload as private-only.** Since 2020, videos
   uploaded via projects that haven't passed YouTube's API audit are locked
   to *private* regardless of the requested privacy. So: default
   `--privacy private`, and document plainly that going public happens in
   YouTube Studio (one click) — or by completing YouTube's audit for the
   user's own project.
3. **Consent screen "Testing" mode expires refresh tokens every 7 days.**
   The guide will recommend setting the user's OAuth consent screen to
   "In production" (staying unverified is fine for personal use — Google
   shows an "unverified app" interstitial once during connect; that's the
   user authorizing their *own* project).

## Phase 1 — Auth foundation (CLI)

- [ ] **1.1 Dependencies**: add `google-auth` + `google-auth-oauthlib`
      (small, pure-Python; handle the loopback browser flow + token
      refresh). Upload itself uses `requests` (already a dependency) via
      YouTube's resumable-upload HTTP protocol — no Google discovery client
      needed. Lazy-imported inside the youtube modules only, per the CLI's
      lazy-import convention; included in the PyInstaller backend.
- [ ] **1.2 Credential storage** (isolation-preserving):
      `<data root>/.mangaeasy/youtube/client_secret.json` (imported copy) +
      `token.json` (access/refresh token). Never logged, never committed;
      `youtube-logout` deletes the token (and `--forget-client` the client
      copy too).
- [ ] **1.3 `mangaeasy youtube-auth`** — connect flow:
      `--client-secrets <path>` imports the user's file on first run; then
      opens the browser to Google's consent page with a localhost loopback
      redirect; `--no-browser` prints the URL instead (headless/SSH).
      Scopes: `youtube.upload` + `youtube.readonly` (the second only to
      show "connected as <channel name>" — see decision D3).
- [ ] **1.4 `mangaeasy youtube-status [--json]`** — connected or not,
      channel title/ID, client-secrets present or missing, token expiry;
      the GUI and agents key off this.
- [ ] **1.5 `mangaeasy youtube-logout`** — revoke (best-effort) + delete
      the stored token.

## Phase 2 — Upload command (CLI)

- [ ] **2.1 `mangaeasy youtube-upload`** flags:
      `--video <path>` (required) · `--title` (required) ·
      `--description` / `--description-file` · `--tags a,b,c` ·
      `--privacy private|unlisted|public` (default **private**, see fact 2)
      · `--category <id>` (default 1, Film & Animation) ·
      `--thumbnail <img>` (set after upload; needs channel thumbnail perm)
      · `--playlist-id` (optional; needs extra scope — v1: omit, note in
      docs) · `--json`.
- [ ] **2.2 Resumable upload** with chunked PUTs, automatic resume/retry on
      transient errors, `MANGAEASY_PROGRESS n/m` bytes-based progress
      lines, and a final `MANGAEASY_RESULT {"video_id": "...", "url":
      "https://youtu.be/..."}` — consistent with the v1.1.0 machine
      contract.
- [ ] **2.3 Clear failure modes** (exit 1 + one actionable line): not
      authenticated → "run mangaeasy youtube-auth"; quota exceeded →
      explain the 1,600-units-per-upload budget; token revoked → reconnect;
      file missing/not a video → say so.
- [ ] **2.4 Tests** (no network): token-store round-trip, request-building
      (metadata JSON, chunk headers), progress/result line emission with a
      mocked HTTP layer, exit codes, `--json` shapes. Real uploads are
      user-side only (needs their credentials).

## Phase 3 — GUI (desktop app)

- [ ] **3.1 Setup tab → "YouTube account" section**: status line via
      `youtube-status --json` ("Connected as <channel>" / "Not connected"),
      **Connect** (file-picker for `client_secret.json` on first run, then
      runs `youtube-auth` as a job — the browser opens for consent),
      **Disconnect**, and an "Open setup guide" link to `docs/youtube.md`
      (the Google Cloud walkthrough).
- [ ] **3.2 Batch tab → "Upload to YouTube" step**: reuses the existing
      long-video picker (`batch:list-videos`, defaults to the latest join),
      fields for title (pre-filled from project name), description, tags,
      privacy dropdown (default private, with a hint about the
      private-lock policy), then runs `youtube-upload` with live progress
      in the terminal pane. Disabled with a hint when not connected.
- [ ] **3.3 IPC/preload/types additions** for status + the two flows,
      following the existing thin-wrapper pattern.

## Phase 4 — MCP + agent contract

- [ ] **4.1 New MCP tools**: `youtube_status`, `youtube_upload`
      (video path, title, description, tags, privacy) — same shell-out
      pattern; `youtube_auth` is deliberately NOT exposed over MCP (it
      needs a human in a browser; agents get a clear "run youtube-auth
      yourself" error from status/upload instead).
- [ ] **4.2 ai-guide.md**: new "Uploading to YouTube" section — auth
      preconditions, the upload recipe, result marker, quota + private-lock
      caveats. The docs cross-ref test keeps it honest automatically.

## Phase 5 — Documentation + ship

- [ ] **5.1 `docs/youtube.md`** — the user-facing walkthrough (the hard
      part): create a Google Cloud project → enable YouTube Data API v3 →
      configure the OAuth consent screen (External, **In production**,
      unverified is fine) → create an "OAuth client ID → Desktop app" →
      download `client_secret.json` → connect in mangaEasy. Plus: quota
      math (~6 uploads/day), why videos arrive private (audit policy),
      7-day token expiry if left in Testing mode, where tokens live, how to
      disconnect/revoke (Google account permissions page).
- [ ] **5.2 README**: feature bullet + link; **CHANGELOG** v1.2.0 entry;
      CLAUDE.md note (auth/token storage layout, new commands, "never log
      tokens").
- [ ] **5.3 Verify + release**: pytest/ruff/typecheck/lint green; manual
      end-to-end by the owner (needs your Google account — I can't do the
      browser consent); then `scripts/release.py 1.2.0 --tag`, push, tag →
      GitHub release v1.2.0.

## Decisions needed (D1–D3)

- **D1 — Bring-your-own Google credentials**: confirm you accept the
  10-minute one-time Google Cloud setup per user (the only viable design;
  the guide makes it painless).
- **D2 — Default privacy `private`**: recommended (uploads from unaudited
  projects are forced private anyway; users publish in Studio). OK?
- **D3 — Also request the read-only scope** so the GUI can show
  "Connected as <channel name>"? Recommended yes; strict-minimal
  alternative is upload-only scope and no channel name shown.

## Size & order

Phases 1→2 are the core (one new `mangaeasy/youtube/` package with
`auth.py` + `upload.py`, three CLI entries). 3 is a moderate GUI pass,
4 is small, 5 is writing. Ships as **v1.2.0**, no breaking changes.
