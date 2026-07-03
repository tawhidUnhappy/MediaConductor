"""YouTube integration: storage snapshot, upload building blocks, CLI exit
codes, and MCP arg mapping — all offline (no Google account needed)."""

import json
import subprocess
import sys

import pytest

from mangaeasy.mcp_server import _build_args
from mangaeasy.youtube import store
from mangaeasy.youtube.upload import build_metadata, content_range, friendly_api_error, parse_tags


def run_cli(env_home, *args: str) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    env["MANGAEASY_HOME"] = str(env_home)
    return subprocess.run(
        [sys.executable, "-m", "mangaeasy.cli", *args],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
    )


def test_status_snapshot_disconnected(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGAEASY_HOME", str(tmp_path))
    snapshot = store.status_snapshot()
    assert snapshot["connected"] is False
    assert snapshot["client_secrets_present"] is False
    assert snapshot["channel_title"] is None


def test_status_snapshot_connected(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGAEASY_HOME", str(tmp_path))
    store.write_json(store.token_path(), {"refresh_token": "r", "scopes": store.SCOPES})
    store.write_json(store.channel_cache_path(), {"id": "UC123", "title": "My Channel"})
    snapshot = store.status_snapshot()
    assert snapshot["connected"] is True
    assert snapshot["channel_title"] == "My Channel"
    assert snapshot["scopes"] == store.SCOPES


def test_status_json_cli(tmp_path):
    proc = run_cli(tmp_path, "youtube-status", "--json")
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["connected"] is False


def test_upload_without_auth_fails_actionably(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    proc = run_cli(tmp_path, "youtube-upload", "--video", str(video), "--title", "t")
    assert proc.returncode == 1
    assert "youtube-auth" in proc.stderr


def test_auth_without_client_secrets_fails_actionably(tmp_path):
    proc = run_cli(tmp_path, "youtube-auth")
    assert proc.returncode == 1
    assert "client_secret.json" in proc.stderr


def test_logout_is_safe_when_disconnected(tmp_path):
    proc = run_cli(tmp_path, "youtube-logout")
    assert proc.returncode == 0
    assert "Nothing to disconnect" in proc.stdout


def test_build_metadata_shape():
    meta = build_metadata("Title", "Desc", ["a", "b"], "24", "unlisted", False)
    assert meta == {
        "snippet": {"title": "Title", "description": "Desc", "categoryId": "24", "tags": ["a", "b"]},
        "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False},
    }
    assert "tags" not in build_metadata("T", "", [], "1", "private", False)["snippet"]


def test_parse_tags():
    assert parse_tags("manga, recap ,, x") == ["manga", "recap", "x"]
    assert parse_tags("") == []


def test_content_range():
    assert content_range(0, 100, 1000) == "bytes 0-99/1000"
    assert content_range(900, 100, 1000) == "bytes 900-999/1000"


def test_friendly_api_error_quota():
    body = json.dumps({"error": {"message": "Quota exceeded",
                                 "errors": [{"reason": "quotaExceeded"}]}})
    text = friendly_api_error(403, body)
    assert "quotaExceeded" in text
    assert "1,600" in text


def test_friendly_api_error_non_json():
    assert "YouTube API error 500" in friendly_api_error(500, "<html>oops</html>")


def test_mcp_upload_args():
    args = _build_args("youtube_upload", {
        "video": "/v.mp4", "title": "T", "tags": "a,b", "privacy": "unlisted",
    })
    assert args == ["--video", "/v.mp4", "--title", "T", "--tags", "a,b",
                    "--privacy", "unlisted", "--json"]
    with pytest.raises(ValueError):
        _build_args("youtube_upload", {"video": "/v.mp4"})  # title missing


def test_mcp_status_args():
    assert _build_args("youtube_status", {}) == ["--json"]
    assert _build_args("youtube_status", {"verify": True}) == ["--verify", "--json"]


def test_write_client_config_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGAEASY_HOME", str(tmp_path))
    store.write_client_config("abc.apps.googleusercontent.com", "GOCSPX-xyz")
    data = store.read_json(store.client_secret_path())
    installed = data["installed"]
    assert installed["client_id"] == "abc.apps.googleusercontent.com"
    assert installed["client_secret"] == "GOCSPX-xyz"
    assert installed["token_uri"] == "https://oauth2.googleapis.com/token"


def test_looks_like_client_id():
    assert store.looks_like_client_id(
        "123456789012-abcdefghijklmnop.apps.googleusercontent.com"
    )
    assert not store.looks_like_client_id("not-a-client-id")
    assert not store.looks_like_client_id("x.apps.googleusercontent.com")  # too short


def test_auth_paste_requires_both_values(tmp_path):
    proc = run_cli(tmp_path, "youtube-auth", "--client-id", "only-half")
    assert proc.returncode == 1
    assert "together" in proc.stderr


def test_auth_paste_rejects_bad_client_id(tmp_path):
    proc = run_cli(tmp_path, "youtube-auth", "--client-id", "garbage", "--client-secret", "s")
    assert proc.returncode == 1
    assert "apps.googleusercontent.com" in proc.stderr


def test_auth_rejects_file_and_paste_together(tmp_path):
    secrets = tmp_path / "cs.json"
    secrets.write_text("{}", encoding="utf-8")
    proc = run_cli(
        tmp_path, "youtube-auth", "--client-secrets", str(secrets),
        "--client-id", "123456789012-abcdefghijklmnop.apps.googleusercontent.com",
        "--client-secret", "s",
    )
    assert proc.returncode == 1
    assert "not both" in proc.stderr


def test_status_verify_when_disconnected(tmp_path):
    proc = run_cli(tmp_path, "youtube-status", "--verify", "--json")
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["verified"] is False
    assert data["verify_error"] == "not connected"
