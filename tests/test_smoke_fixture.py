"""Tests for the smoke-test fixture builder (the CI-safe, ffmpeg-free part)."""

from __future__ import annotations

import json

from mangaeasy.tools.smoke import NARRATION, build_fixture_project


def test_build_fixture_project_layout(tmp_path):
    project_root = build_fixture_project(tmp_path)
    assert project_root == tmp_path / "library" / "SmokeTest"
    item = project_root / "01"
    entries = json.loads((item / "narration.json").read_text(encoding="utf-8"))
    assert entries == NARRATION
    for entry in entries:
        panel = item / "panels" / entry["image"]
        assert panel.is_file() and panel.stat().st_size > 0


def test_build_fixture_project_is_idempotent(tmp_path):
    build_fixture_project(tmp_path)
    project_root = build_fixture_project(tmp_path)  # re-run must not raise
    assert (project_root / "01" / "narration.json").is_file()
