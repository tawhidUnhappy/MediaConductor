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

# Full video management (youtube.force-ssl): upload, edit metadata, and
# delete the channel's videos — needed so re-uploads can replace a bad take
# without a trip to YouTube Studio. Tokens granted before this scope was
# added keep working for upload but can't delete; re-run `youtube-auth`
# once to re-consent with the broader permission.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
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


def write_client_config(client_id: str, client_secret: str) -> None:
    """Persist a pasted client id/secret pair as a standard installed-app
    client config — the simple alternative to downloading client_secret.json
    (Google shows both values right in the console's Credentials dialog)."""
    write_json(client_secret_path(), {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    })


def looks_like_client_id(client_id: str) -> bool:
    return client_id.endswith(".apps.googleusercontent.com") and len(client_id) > 40


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
