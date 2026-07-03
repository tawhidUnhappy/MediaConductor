"""`mangaeasy youtube-auth` / `youtube-status` / `youtube-logout`.

Connect flow: the user's own Google OAuth *Desktop app* client
(client_secret.json — see docs/youtube.md for the one-time Google Cloud
setup) drives google-auth-oauthlib's loopback flow: a localhost HTTP
server catches the redirect while the browser shows Google's consent page.
The granted token is stored under the app's own data folder (store.py).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from mangaeasy.youtube import store


def load_credentials():
    """Stored credentials, refreshed if stale. None when not connected.

    Lazy google imports — only auth/upload commands pay for them.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = store.token_path()
    if not path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(path), store.SCOPES)
    except ValueError:
        return None
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        store.write_json(store.token_path(), json.loads(creds.to_json()))
    return creds if creds.valid else None


def _fetch_channel(creds) -> dict:
    """Channel title/id for "connected as ..." — cached for offline status."""
    import requests

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items") or []
    if not items:
        return {}
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def auth_main() -> int:
    parser = argparse.ArgumentParser(
        description="Connect a YouTube account (opens the browser for Google's consent page)."
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=None,
        help="Path to your Google OAuth client_secret.json (Desktop app client). "
             "Imported into the app's data folder on first use; see docs/youtube.md.",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="Alternative to --client-secrets: paste the OAuth client ID shown in the "
             "Google console (ends with .apps.googleusercontent.com). Use with --client-secret.",
    )
    parser.add_argument(
        "--client-secret",
        default=None,
        help="The OAuth client secret shown next to the client ID (not confidential for "
             "Desktop-app clients). Use with --client-id.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open a browser automatically — print the consent URL instead "
             "(the loopback redirect still requires the browser to run on this machine).",
    )
    args = parser.parse_args()

    if (args.client_id is None) != (args.client_secret is None):
        print("ERROR: --client-id and --client-secret must be provided together.", file=sys.stderr)
        return 1
    if args.client_id is not None and args.client_secrets is not None:
        print("ERROR: use either --client-secrets (file) or --client-id/--client-secret (pasted), not both.",
              file=sys.stderr)
        return 1

    if args.client_id is not None:
        client_id = args.client_id.strip()
        client_secret = args.client_secret.strip()
        if not store.looks_like_client_id(client_id):
            print(
                "ERROR: that doesn't look like a Google OAuth client ID "
                "(expected something ending in .apps.googleusercontent.com).\n"
                "Copy it from Google Cloud console -> APIs & Services -> Credentials.",
                file=sys.stderr,
            )
            return 1
        if not client_secret:
            print("ERROR: the client secret is empty.", file=sys.stderr)
            return 1
        store.write_client_config(client_id, client_secret)
        print(f"Saved OAuth client into {store.client_secret_path()}")

    if args.client_secrets is not None:
        source = args.client_secrets.expanduser().resolve()
        if not source.is_file():
            print(f"ERROR: client secrets file not found: {source}", file=sys.stderr)
            return 1
        store.youtube_dir().mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, store.client_secret_path())
        print(f"Imported OAuth client into {store.client_secret_path()}")

    if not store.client_secret_path().exists():
        print(
            "ERROR: no OAuth client configured yet.\n"
            "Create one (free, ~10 minutes, one time) following docs/youtube.md, then run:\n"
            "  mangaeasy youtube-auth --client-secrets /path/to/client_secret.json",
            file=sys.stderr,
        )
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(store.client_secret_path()), store.SCOPES)
    print("Opening Google's consent page — approve access for your channel...", flush=True)
    creds = flow.run_local_server(
        port=0,
        open_browser=not args.no_browser,
        authorization_prompt_message="Visit this URL to authorize mangaEasy:\n{url}",
        success_message="mangaEasy is connected — you can close this tab.",
    )
    store.write_json(store.token_path(), json.loads(creds.to_json()))

    channel = {}
    try:
        channel = _fetch_channel(creds)
        if channel:
            store.write_json(store.channel_cache_path(), channel)
    except Exception as exc:  # noqa: BLE001 — channel name is cosmetic
        print(f"[warn] connected, but could not read the channel name: {exc}")

    who = f" as {channel['title']}" if channel.get("title") else ""
    print(f"\nConnected{who}. Token stored at {store.token_path()}")
    print("Try it: mangaeasy youtube-status")
    return 0


def _verify_live(snapshot: dict) -> dict:
    """Refresh the token and call the API — proves the connection actually
    works right now (not just that files exist). Updates the channel cache."""
    if not snapshot["connected"]:
        return {**snapshot, "verified": False, "verify_error": "not connected"}
    try:
        creds = load_credentials()
        if creds is None:
            return {**snapshot, "verified": False,
                    "verify_error": "stored token is invalid or was revoked — run: mangaeasy youtube-auth"}
        channel = _fetch_channel(creds)
        if channel:
            store.write_json(store.channel_cache_path(), channel)
            snapshot = {**snapshot, "channel_title": channel["title"], "channel_id": channel["id"]}
        return {**snapshot, "verified": True, "verify_error": None}
    except Exception as exc:  # noqa: BLE001 — network/auth failures become a reason string
        return {**snapshot, "verified": False, "verify_error": str(exc)}


def status_main() -> int:
    parser = argparse.ArgumentParser(description="Show YouTube connection status.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    parser.add_argument("--verify", action="store_true",
                        help="Also verify the connection live: refresh the token and query the "
                             "channel (needs network). Adds verified/verify_error to the output.")
    args = parser.parse_args()

    snapshot = store.status_snapshot()
    if args.verify:
        snapshot = _verify_live(snapshot)

    if args.as_json:
        print(json.dumps(snapshot, ensure_ascii=False))
        return 0

    if not snapshot["connected"]:
        print("Not connected.")
        if not snapshot["client_secrets_present"]:
            print("No Google project attached yet either — see docs/youtube.md, then run one of:")
            print("  mangaeasy youtube-auth --client-id <id> --client-secret <secret>")
            print("  mangaeasy youtube-auth --client-secrets /path/to/client_secret.json")
        else:
            print("Run: mangaeasy youtube-auth")
        return 0
    who = snapshot["channel_title"] or "(channel name unknown)"
    print(f"Connected as {who}")
    print(f"  token: {snapshot['token_file']}")
    if args.verify:
        if snapshot.get("verified"):
            print("  verified: yes — token refreshed and channel reachable.")
        else:
            print(f"  verified: NO — {snapshot.get('verify_error')}")
            return 1
    return 0


def logout_main() -> int:
    parser = argparse.ArgumentParser(description="Disconnect the YouTube account (delete the stored token).")
    parser.add_argument("--forget-client", action="store_true",
                        help="Also delete the imported client_secret.json.")
    args = parser.parse_args()

    token = store.read_json(store.token_path())
    if token.get("token") or token.get("refresh_token"):
        # Best-effort revoke; deleting the local token is what matters.
        try:
            import requests

            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token.get("refresh_token") or token.get("token")},
                timeout=15,
            )
        except Exception:  # noqa: BLE001
            pass

    removed = False
    for path in (store.token_path(), store.channel_cache_path()):
        if path.exists():
            path.unlink()
            removed = True
    if args.forget_client and store.client_secret_path().exists():
        store.client_secret_path().unlink()
        print("Deleted the imported OAuth client too.")
    print("Disconnected." if removed else "Nothing to disconnect.")
    return 0
