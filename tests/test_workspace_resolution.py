"""Workspace-root resolution: commands run from the wrong cwd must still find
the registered workspace instead of silently creating a second library/ tree
(the D:\\library incident)."""

from __future__ import annotations

import json
from pathlib import Path

import mediaconductor.config as config


def _make_workspace(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    return path


def test_env_var_wins(tmp_path: Path, monkeypatch):
    workspace = _make_workspace(tmp_path / "ws")
    monkeypatch.setenv("MEDIACONDUCTOR_PROJECT_ROOT", str(workspace))
    assert config._project_root() == workspace.resolve()


def test_cwd_with_config_json_wins_over_registration(tmp_path: Path, monkeypatch):
    cwd_workspace = _make_workspace(tmp_path / "cwd_ws")
    registered = _make_workspace(tmp_path / "registered")
    monkeypatch.delenv("MEDIACONDUCTOR_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "data"))
    assert config.register_workspace(registered) is not None
    monkeypatch.chdir(cwd_workspace)
    assert config._project_root() == cwd_workspace.resolve()


def test_registered_workspace_rescues_a_wrong_cwd(tmp_path: Path, monkeypatch):
    registered = _make_workspace(tmp_path / "registered")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("MEDIACONDUCTOR_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "data"))
    marker = config.register_workspace(registered)
    assert marker is not None and json.loads(marker.read_text(encoding="utf-8"))[
        "workspace_root"] == str(registered.resolve())
    monkeypatch.chdir(elsewhere)
    assert config._project_root() == registered.resolve()


def test_stale_registration_is_ignored(tmp_path: Path, monkeypatch):
    registered = _make_workspace(tmp_path / "registered")
    monkeypatch.delenv("MEDIACONDUCTOR_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "data"))
    assert config.register_workspace(registered) is not None
    (registered / "config.json").unlink()  # workspace was deleted/moved
    assert config._registered_workspace() is None


def test_register_workspace_refuses_non_workspaces(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "data"))
    assert config.register_workspace(tmp_path / "no_config") is None


# ── A fresh clone has no config.json ─────────────────────────────────────────
# Found by cloning the repo onto a wiped disk and following docs/setup.md:
# config.json is gitignored, so a just-cloned checkout has none, and requiring
# it made `setup` register nothing at all. Every later command run from
# another directory then resolved its data root to *that* directory — the
# exact second-library-tree incident this whole mechanism exists to prevent.

def _make_fresh_clone(path: Path) -> Path:
    """A checkout as `git clone` leaves it: no config.json, no data/."""
    (path / "mediaconductor").mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text("[project]\nname='media-conductor'\n",
                                         encoding="utf-8")
    return path


def test_a_fresh_clone_is_a_registerable_workspace(tmp_path: Path, monkeypatch):
    clone = _make_fresh_clone(tmp_path / "clone")
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "home"))
    assert config.looks_like_workspace(clone)
    assert config.register_workspace(clone) is not None


def test_a_workspace_that_only_has_data_still_counts(tmp_path: Path, monkeypatch):
    """A frozen install has no pyproject.toml; its evidence is data/."""
    produced = tmp_path / "produced"
    (produced / "data").mkdir(parents=True)
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "home"))
    assert config.looks_like_workspace(produced)
    assert config.register_workspace(produced) is not None


def test_a_fresh_clone_rescues_a_wrong_cwd(tmp_path: Path, monkeypatch):
    """The end-to-end guarantee docs/setup.md promises, on a clone."""
    clone = _make_fresh_clone(tmp_path / "clone")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("MEDIACONDUCTOR_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("MEDIACONDUCTOR_HOME", str(tmp_path / "home"))
    assert config.register_workspace(clone) is not None
    monkeypatch.chdir(elsewhere)
    assert config._project_root() == clone.resolve()


def test_an_arbitrary_directory_is_still_not_a_workspace(tmp_path: Path):
    """The relaxation must not make every cwd look like a workspace."""
    plain = tmp_path / "downloads"
    plain.mkdir()
    assert not config.looks_like_workspace(plain)
    # A pyproject alone is some other project, not a MediaConductor checkout.
    (plain / "pyproject.toml").write_text("[project]\nname='something-else'\n",
                                          encoding="utf-8")
    assert not config.looks_like_workspace(plain)
