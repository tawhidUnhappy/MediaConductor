"""Repository-context guards for generated, user-owned media projects."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative_path",
    [
        "projects/story-demo/images/scene-001.png",
        "projects/story-demo/render/final-story.mp4",
        "projects/song-demo/audio/generated-song.wav",
        "projects/song-demo/stems/vocals.flac",
    ],
)
def test_generated_projects_are_git_ignored(relative_path: str):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", relative_path],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, f"expected Git to ignore {relative_path}"


def test_generated_projects_are_excluded_from_docker_context():
    docker_rules = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "/projects/" in docker_rules


def test_build_products_are_excluded_from_docker_context():
    docker_rules = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {"/build/", "/dist/"} <= docker_rules


def test_sdist_allowlist_does_not_include_generated_projects():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"/projects"' not in pyproject


def test_no_raw_subprocess_spawns_outside_runtime():
    """Every child process must go through mediaconductor.runtime.run/popen.

    A raw subprocess spawn skips the CREATE_NO_WINDOW handling and pops a
    blank console window on Windows whenever the parent has no visible
    console (detached jobs, MCP servers started by an editor). runtime.py
    owns the flags; assets/tools scripts run inside external envs and are
    launched (not spawned from) here.
    """
    package = ROOT / "mediaconductor"
    forbidden = (
        "subprocess.run(", "subprocess.Popen(", "subprocess.call(",
        "subprocess.check_call(", "subprocess.check_output(",
        "os.system(", "os.popen(",
    )
    offenders: list[str] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        if relative == "runtime.py" or relative.startswith("assets/"):
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{relative}: {token}")
    assert not offenders, (
        "raw subprocess spawn(s) found; use mediaconductor.runtime.run/popen instead:\n"
        + "\n".join(offenders)
    )
