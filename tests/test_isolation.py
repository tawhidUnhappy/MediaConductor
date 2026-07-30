"""Everything this install writes must stay inside the install folder.

The promise is "delete the folder and the machine is as it was". Breaking it is
silent and expensive: uv's wheel cache and downloaded interpreters, and Hugging
Face's model weights, all default to ``$HOME`` and add up to tens of gigabytes
that nobody finds again.

The awkward part is that the environment has to be pinned in *two* languages.
``uv sync`` downloads the interpreter and every wheel before any of our Python
runs, so the launchers must export the same variables in shell that
:mod:`mangaeasy.isolation` sets in Python. Two copies drift, and the drift is
invisible until someone's home directory fills up — so most of this file exists
to assert the copies still agree, character for character where it matters.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from mangaeasy import isolation
from mangaeasy.tools.external import ENV_TARGET_VARS, app_root, tool_env
from mangaeasy.tools.vendored import UV_ASSETS, UV_VERSION, download_manifest

ROOT = Path(__file__).resolve().parent.parent
ISOLATE_SH = ROOT / "scripts" / "isolate.sh"
ISOLATE_CMD = ROOT / "scripts" / "isolate.cmd"
BOOTSTRAP_SH = ROOT / "bootstrap.sh"
BOOTSTRAP_PS1 = ROOT / "bootstrap.ps1"

# Variables that must be pinned everywhere. Derived from isolation.py so adding
# one there makes the shell-parity tests below fail until the scripts follow.
PINNED = [variable for variable, _name, _sub in isolation.CACHE_ENV]


# ── The Python side ───────────────────────────────────────────────────────────

def test_every_cache_resolves_inside_the_install_folder():
    root = app_root().resolve()
    for variable, path in isolation.cache_paths().items():
        assert path.resolve().is_relative_to(root), f"{variable} escapes {root}: {path}"


def test_cache_env_covers_the_big_three_downloaders():
    """uv wheels, uv interpreters and HF weights are the volume; never drop them."""
    for variable in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "HF_HOME"):
        assert variable in PINNED


def test_pinning_overrides_an_ambient_cache_var(monkeypatch):
    """An exported HF_HOME for another project must not win.

    This is the whole reason the vars are force-set rather than setdefault:
    inheriting one silently redirects multi-GB model downloads onto another
    disk, and the failure surfaces much later as a missing model.
    """
    monkeypatch.setenv("HF_HOME", "/somewhere/else")
    monkeypatch.setenv("UV_CACHE_DIR", "/somewhere/else/uv")
    monkeypatch.delenv(isolation.SHARE_CACHES_VAR, raising=False)
    env = isolation.isolation_env()
    assert env["HF_HOME"] == str(isolation.cache_paths()["HF_HOME"])
    assert env["UV_CACHE_DIR"] == str(isolation.cache_paths()["UV_CACHE_DIR"])


def test_share_caches_opt_out_defers_to_the_ambient_value(monkeypatch):
    monkeypatch.setenv("HF_HOME", "/shared/hf")
    monkeypatch.setenv(isolation.SHARE_CACHES_VAR, "1")
    assert isolation.isolation_env()["HF_HOME"] == "/shared/hf"


def test_share_caches_still_fills_in_what_is_absent(monkeypatch):
    monkeypatch.delenv("TRITON_CACHE_DIR", raising=False)
    monkeypatch.setenv(isolation.SHARE_CACHES_VAR, "1")
    env = isolation.isolation_env()
    assert env["TRITON_CACHE_DIR"] == str(isolation.cache_paths()["TRITON_CACHE_DIR"])


def test_apply_pins_the_current_process(monkeypatch):
    monkeypatch.setenv("HF_HOME", "/somewhere/else")
    monkeypatch.delenv(isolation.SHARE_CACHES_VAR, raising=False)
    isolation.apply()
    assert os.environ["HF_HOME"] == str(isolation.cache_paths()["HF_HOME"])


def test_report_is_clean_by_default(monkeypatch):
    monkeypatch.delenv(isolation.SHARE_CACHES_VAR, raising=False)
    for variable in PINNED:
        monkeypatch.delenv(variable, raising=False)
    report = isolation.isolation_report()
    assert report["isolated"], report["escaping"]
    assert report["escaping"] == {}


def test_report_names_what_escapes(monkeypatch):
    """A leak must be reported, not silently tolerated."""
    monkeypatch.setenv(isolation.SHARE_CACHES_VAR, "1")
    monkeypatch.setenv("HF_HOME", "/tmp/elsewhere/hf")
    report = isolation.isolation_report()
    assert not report["isolated"]
    assert report["escaping"]["HF_HOME"] == "/tmp/elsewhere/hf"


def test_tool_env_still_pins_every_cache(monkeypatch):
    """Regression guard: tool_env() delegates to isolation now."""
    monkeypatch.delenv(isolation.SHARE_CACHES_VAR, raising=False)
    env = tool_env()
    for variable, path in isolation.cache_paths().items():
        assert env[variable] == str(path)
    # And it keeps its own contract on top.
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    assert "VIRTUAL_ENV" not in tool_env()


def test_ensure_cache_dirs_creates_them(monkeypatch, tmp_path):
    monkeypatch.setenv("MANGAEASY_HOME", str(tmp_path / "runtime"))
    created = isolation.ensure_cache_dirs()
    assert created and all(path.is_dir() for path in created)


# ── Shell parity: the two halves must not drift ───────────────────────────────

def test_isolate_sh_pins_exactly_the_python_variables():
    text = ISOLATE_SH.read_text(encoding="utf-8")
    for variable in PINNED:
        assert re.search(rf'^\s*{variable}="\$_me_cache/', text, re.M), (
            f"scripts/isolate.sh does not pin {variable} — it must, because "
            f"`uv sync` runs before mangaeasy.isolation can act"
        )
        assert re.search(rf'\b{variable}\b', text)


def test_isolate_sh_and_python_agree_on_every_path():
    """Compare the values the shell actually exports against isolation.py.

    Parses the assignments rather than executing bash so the test runs on
    Windows too — where this file is exactly what a reviewer cannot try by hand.
    """
    text = ISOLATE_SH.read_text(encoding="utf-8")
    expected = isolation.cache_paths()
    root = app_root()
    for variable, path in expected.items():
        match = re.search(rf'^\s*{variable}="\$_me_cache/(?P<tail>[^"]+)"', text, re.M)
        assert match, f"no forcing assignment for {variable} in isolate.sh"
        shell_path = Path(str(root)) / "runtime" / "cache" / match.group("tail")
        assert shell_path == path, (
            f"{variable}: isolate.sh says {shell_path}, isolation.py says {path}"
        )


def test_isolate_cmd_pins_exactly_the_python_variables():
    text = ISOLATE_CMD.read_text(encoding="utf-8")
    for variable in PINNED:
        assert f'set "{variable}=%_ME_CACHE%' in text, (
            f"scripts/isolate.cmd does not pin {variable}"
        )


def test_bootstrap_ps1_pins_exactly_the_python_variables():
    text = BOOTSTRAP_PS1.read_text(encoding="utf-8")
    for variable in PINNED:
        assert f"'{variable}'" in text, f"bootstrap.ps1 does not pin {variable}"


def test_shell_halves_pin_the_venv_location():
    """An inherited UV_PROJECT_ENVIRONMENT could put .venv outside the folder."""
    assert "UV_PROJECT_ENVIRONMENT" in ISOLATE_SH.read_text(encoding="utf-8")
    assert "UV_PROJECT_ENVIRONMENT" in ISOLATE_CMD.read_text(encoding="utf-8")
    assert "UV_PROJECT_ENVIRONMENT" in BOOTSTRAP_PS1.read_text(encoding="utf-8")


def test_launchers_source_the_shared_isolation_snippet():
    """run.sh/run.bat must not hand-roll their own copy of the pinning."""
    assert "scripts/isolate.sh" in (ROOT / "run.sh").read_text(encoding="utf-8")
    assert r"scripts\isolate.cmd" in (ROOT / "run.bat").read_text(encoding="utf-8")
    assert "scripts/isolate.sh" in BOOTSTRAP_SH.read_text(encoding="utf-8")


# ── Bootstrap pins the same portable uv the downloader verifies ───────────────

def test_bootstrap_scripts_pin_the_same_uv_version():
    for script in (BOOTSTRAP_SH, BOOTSTRAP_PS1):
        text = script.read_text(encoding="utf-8")
        assert UV_VERSION in text, (
            f"{script.name} does not pin uv {UV_VERSION} — it must match "
            f"UV_VERSION in mangaeasy/tools/vendored.py"
        )


@pytest.mark.parametrize(("system", "arch"), sorted(UV_ASSETS))
def test_bootstrap_sh_carries_the_verified_digest(system, arch):
    """The bootstrap runs a downloaded binary, so its digest must be the pinned one."""
    if system == "windows":
        text = BOOTSTRAP_PS1.read_text(encoding="utf-8")
    else:
        text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    asset, sha256 = UV_ASSETS[(system, arch)]
    if system == "windows" and arch != "x64":
        pytest.skip("bootstrap.ps1 only supports x64 Windows")
    assert asset in text, f"{asset} missing from the bootstrap script"
    assert sha256 in text, f"digest for {asset} missing or stale in the bootstrap script"


def test_bootstrap_refuses_an_unverified_download():
    """A digest mismatch must abort, never fall through to executing the file."""
    text = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert "SHA-256 mismatch" in text
    assert re.search(r'if \[ "\$got" != "\$UV_SHA" \]', text)
    ps1 = BOOTSTRAP_PS1.read_text(encoding="utf-8")
    assert "SHA-256 mismatch" in ps1
    assert "$got -ne $UvSha" in ps1


# ── The published download manifest ──────────────────────────────────────────

def test_manifest_defaults_to_this_machine():
    manifest = download_manifest()
    assert manifest["downloads"], "no downloads for this platform"
    for entry in manifest["downloads"]:
        assert entry["system"] == manifest["this_system"]
        assert entry["arch"] == manifest["this_arch"]


def test_manifest_all_platforms_covers_every_tool_and_os():
    manifest = download_manifest(all_platforms=True)
    tools = {entry["tool"] for entry in manifest["downloads"]}
    assert tools == {"ffmpeg", "uv", "git-lfs"}
    systems = {entry["system"] for entry in manifest["downloads"]}
    assert systems == {"windows", "linux", "darwin"}


def test_manifest_urls_are_https_and_digests_well_formed():
    for entry in download_manifest(all_platforms=True)["downloads"]:
        assert entry["url"].startswith("https://"), entry
        if entry["sha256"] is not None:
            assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), entry
        else:
            # Only the rolling ffmpeg builds may be unpinned, and they must say why.
            assert entry["tool"] == "ffmpeg" and entry.get("note"), entry


def test_manifest_installs_into_the_install_folder():
    manifest = download_manifest()
    assert Path(manifest["install_dir"]).is_relative_to(app_root())


def test_manifest_digests_match_the_downloader_tables():
    """The documented links must be the ones the code actually fetches."""
    by_key = {
        (e["system"], e["arch"]): e
        for e in download_manifest(all_platforms=True)["downloads"]
        if e["tool"] == "uv"
    }
    for key, (asset, sha256) in UV_ASSETS.items():
        assert by_key[key]["sha256"] == sha256
        assert by_key[key]["url"].endswith(asset)


# ── Portable-first ───────────────────────────────────────────────────────────

def test_core_tools_are_portable_first():
    """A system ffmpeg is outside the folder, so it must not be preferred.

    Accepting one made renders depend on whichever encoders that build happened
    to have, and broke the "delete the folder" promise.
    """
    import inspect

    from mangaeasy.tools.vendored import ensure_core_tools

    signature = inspect.signature(ensure_core_tools)
    assert signature.parameters["prefer_portable"].default is True


# ── Tool subprocesses must never inherit an environment TARGET ────────────────

def test_tool_env_drops_every_environment_target(monkeypatch):
    """An inherited env target redirects a tool's install into the main venv.

    UV_PROJECT_ENVIRONMENT is the dangerous one: scripts/isolate.sh sets it so
    the main venv cannot be relocated, but `install-tool` runs `uv sync` inside
    the tool's own project dir. Inherited, that sync targeted mangaEasy's venv —
    it installed kokoro + torch there and, resolving to kokoro's lockfile,
    uninstalled the `mangaeasy` package itself, leaving the CLI unrunnable and
    the tool dir with no venv (2026-07-30).
    """
    for variable in ENV_TARGET_VARS:
        monkeypatch.setenv(variable, "/some/other/env")
    env = tool_env()
    leaked = [v for v in ENV_TARGET_VARS if v in env]
    assert not leaked, (
        f"tool_env() leaked environment target(s) {leaked} into an isolated "
        f"tool subprocess; each one redirects that tool's uv/python at the "
        f"wrong environment"
    )


def test_env_target_vars_covers_uv_project_environment():
    """isolate.sh exports it, so tool_env() must know to strip it."""
    assert "UV_PROJECT_ENVIRONMENT" in ENV_TARGET_VARS
    assert "UV_PROJECT_ENVIRONMENT" in ISOLATE_SH.read_text(encoding="utf-8")


def test_every_env_target_the_shell_exports_is_stripped():
    """Anything isolate.sh exports that names an environment must be dropped.

    Catches the general shape of the bug: adding a new redirecting variable to
    the shell half without teaching tool_env() to strip it.
    """
    text = ISOLATE_SH.read_text(encoding="utf-8")
    exported = set(re.findall(r"export ([A-Z_]+)", text))
    exported |= set(re.findall(r"^([A-Z_]+)=", text, re.M))
    targets = {v for v in exported
               if v.endswith("_ENVIRONMENT") or v in {"VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"}}
    missing = targets - set(ENV_TARGET_VARS)
    assert not missing, (
        f"scripts/isolate.sh exports {sorted(missing)}, which name an "
        f"environment but are not in ENV_TARGET_VARS — a tool's `uv sync` "
        f"would target mangaEasy's own venv"
    )
