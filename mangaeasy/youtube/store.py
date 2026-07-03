"""Credential storage for the YouTube integration.

Everything lives in this install's own data folder
(`<data root>/.mangaeasy/youtube/`) — nothing under the user's home or the
system keyring, matching the app-wide isolation promise:

- ``client_secret.json`` — the user's own Google OAuth client (imported once
  via `youtube-auth --client-secrets`; see docs/youtube.md for how to
  create it).
- ``token.json`` — the granted access/refresh token (google-auth's
  authorized-user format).
- ``channel.json`` — cached channel title/id captured at connect time so
  `youtube-status` can answer offline.

Tokens are secrets: never print or log their contents, only paths/booleans.
Plain JSON file helpers only — the google-auth imports stay inside auth.py
so the rest of the CLI never pays for them (lazy-import convention).
"""

from __future__ import annotations

import json
from pathlib import Path

from mangaeasy.tools.external import mangaeasy_home

# Upload permission + read-only (the latter only to show "connected as
# <channel>"; no channel-management scope is ever requested).
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def youtube_dir() -> Path:
    return mangaeasy_home() / "youtube"


def client_secret_path() -> Path:
    return youtube_dir() / "client_secret.json"


def token_path() -> Path:
    return youtube_dir() / "token.json"


def channel_cache_path() -> Path:
    return youtube_dir() / "channel.json"


def read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def status_snapshot() -> dict:
    """Offline status: what exists on disk (no network, no google imports)."""
    channel = read_json(channel_cache_path())
    token = read_json(token_path())
    return {
        "connected": bool(token.get("refresh_token")),
        "client_secrets_present": client_secret_path().exists(),
        "channel_title": channel.get("title"),
        "channel_id": channel.get("id"),
        "scopes": token.get("scopes") or [],
        "token_file": str(token_path()),
    }
