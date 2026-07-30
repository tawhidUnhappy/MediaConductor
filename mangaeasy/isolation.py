"""mangaeasy.isolation — everything this install writes stays in its own folder.

One rule: **nothing mangaEasy runs may write outside the install directory.**
Not the wheel cache, not a 6 GB model download, not a Triton kernel cache, not
a downloaded Python interpreter. Delete the folder and the machine is exactly
as it was.

That is not the default for any of the tools involved. `uv` caches wheels in
``~/.cache/uv`` and installs interpreters under ``~/.local/share/uv/python``;
Hugging Face writes to ``~/.cache/huggingface``; torch, Triton and Inductor
each have their own home-directory cache. Left alone they scatter tens of
gigabytes across ``$HOME`` — and worse, an ambient ``HF_HOME`` the user
exported for some *other* project silently redirects this install's model
downloads onto another disk.

So the cache variables here are **force-set**, overriding whatever the ambient
environment says, in two places that together cover every process:

* :func:`apply` runs at CLI startup (``cli.py``), pinning mangaEasy's own
  process and therefore everything it spawns.
* the launchers (``run.sh``/``run.bat``/``bootstrap.*``) export the same values
  *before* the first ``uv sync``, because that one runs before any Python does
  — historically the single biggest leak, since it is what downloads the
  interpreter and every wheel.

:func:`shell_exports` renders the identical set for those shells, so there is
one definition rather than three drifting copies.

``MANGAEASY_SHARE_CACHES=1`` opts out: values are then only filled in when
absent, which is what someone deliberately sharing one model cache across
several checkouts wants. It is not the default because the cost of guessing
wrong is a support thread about a missing 6 GB download.
"""

from __future__ import annotations

import os
from pathlib import Path

# Env var -> the cache_dir() name it points at, plus an optional subpath.
# Every entry is a documented variable of the tool that reads it; adding a
# tool means adding its variable here, not a second pinning mechanism.
CACHE_ENV: tuple[tuple[str, str, str | None], ...] = (
    # uv: wheel/source cache and the interpreters it downloads. These two are
    # the ones that matter most — they are consumed before Python starts.
    ("UV_CACHE_DIR", "uv", None),
    ("UV_PYTHON_INSTALL_DIR", "uv_python", None),
    # Hugging Face: model weights. The largest single consumer by volume.
    ("HF_HOME", "hf", None),
    ("HF_HUB_CACHE", "hf", "hub"),
    ("TRANSFORMERS_CACHE", "hf", "hub"),
    # torch and its compilers.
    ("TORCH_HOME", "torch", None),
    ("TORCH_EXTENSIONS_DIR", "torch_extensions", None),
    ("TORCHINDUCTOR_CACHE_DIR", "torchinductor", None),
    ("TRITON_CACHE_DIR", "triton", None),
    # Catch-all for tools that ignore everything above.
    ("XDG_CACHE_HOME", "xdg", None),
)

# Not paths — defaults that make isolated runs quieter and reproducible.
# setdefault semantics: a user who explicitly wants telemetry keeps it.
BEHAVIOUR_ENV: tuple[tuple[str, str], ...] = (
    ("HF_HUB_DISABLE_TELEMETRY", "1"),
    ("HF_XET_HIGH_PERFORMANCE", "1"),
    ("TOKENIZERS_PARALLELISM", "false"),
)

SHARE_CACHES_VAR = "MANGAEASY_SHARE_CACHES"


def share_caches() -> bool:
    """True when the user opted into inheriting ambient cache locations."""
    return os.environ.get(SHARE_CACHES_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def cache_paths() -> dict[str, Path]:
    """Env var -> absolute folder-local path, for every pinned cache."""
    from mangaeasy.layout import cache_dir

    resolved: dict[str, Path] = {}
    for variable, name, subpath in CACHE_ENV:
        base = cache_dir(name)
        resolved[variable] = base / subpath if subpath else base
    return resolved


def isolation_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """*base* (default ``os.environ``) with every cache pinned inside the install.

    Returns a new dict; nothing is mutated. Use :func:`apply` to change the
    current process.
    """
    env = dict(base if base is not None else os.environ)
    # setdefault when sharing was requested, hard override otherwise — the
    # whole point is that an inherited HF_HOME must not win by accident.
    assign = env.setdefault if share_caches() else env.__setitem__
    for variable, path in cache_paths().items():
        assign(variable, str(path))
    for variable, value in BEHAVIOUR_ENV:
        env.setdefault(variable, value)
    return env


def apply() -> None:
    """Pin this process' caches, so every child it spawns inherits them.

    Called once from ``cli.py`` before any command runs. Cheap: string work
    plus path joins, no filesystem or network access.
    """
    os.environ.update(isolation_env())


def ensure_cache_dirs() -> list[Path]:
    """Create every pinned cache folder; return them.

    Some tools fail confusingly rather than helpfully when handed a cache path
    whose parent does not exist, so `setup` materialises them up front.
    """
    created = []
    for path in sorted(set(cache_paths().values())):
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created


def _is_inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def isolation_report() -> dict:
    """Whether this install is actually self-contained, and what escapes.

    Surfaced by ``doctor`` and ``where``. The check is deliberately about the
    *effective* environment rather than our intent: if something exported
    ``HF_HOME`` after startup, or ``MANGAEASY_SHARE_CACHES=1`` is set, this
    reports the truth instead of the policy.
    """
    from mangaeasy.layout import data_root, runtime_root
    from mangaeasy.tools.external import app_root

    root = app_root()
    escaping: dict[str, str] = {}
    effective: dict[str, str] = {}
    for variable, expected in cache_paths().items():
        actual = os.environ.get(variable) or str(expected)
        effective[variable] = actual
        if not _is_inside(Path(actual), root):
            escaping[variable] = actual

    trees = {"data": data_root(), "runtime": runtime_root()}
    for label, path in trees.items():
        if not _is_inside(path, root):
            escaping[f"<{label} root>"] = str(path)

    return {
        "install_root": str(root),
        "isolated": not escaping,
        "share_caches": share_caches(),
        "caches": effective,
        "escaping": escaping,
        "data_root": str(data_root()),
        "runtime_root": str(runtime_root()),
    }


# ── Rendering the same values for shells ──────────────────────────────────────

def _quote_sh(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def shell_exports(shell: str) -> str:
    """The pinned environment as a sourceable snippet for *shell*.

    ``sh`` (bash/zsh), ``bat`` (cmd.exe) and ``ps1`` (PowerShell). The
    launchers consume this so the shell side and the Python side can never
    disagree about where the uv cache lives.
    """
    paths = cache_paths()
    lines: list[str] = []
    if shell == "sh":
        for variable, path in paths.items():
            lines.append(f"export {variable}={_quote_sh(str(path))}")
        for variable, value in BEHAVIOUR_ENV:
            lines.append(f': "${{{variable}:={value}}}"; export {variable}')
    elif shell == "bat":
        for variable, path in paths.items():
            lines.append(f'set "{variable}={path}"')
        for variable, value in BEHAVIOUR_ENV:
            lines.append(f'if not defined {variable} set "{variable}={value}"')
    elif shell == "ps1":
        for variable, path in paths.items():
            lines.append(f'$env:{variable} = "{path}"')
        for variable, value in BEHAVIOUR_ENV:
            lines.append(
                f'if (-not $env:{variable}) {{ $env:{variable} = "{value}" }}'
            )
    else:
        raise ValueError(f"unknown shell {shell!r}; expected sh, bat or ps1")
    return "\n".join(lines) + "\n"


def main() -> int:
    """``mangaeasy env`` — print this install's pinned environment.

    For a human setting up a shell, a CI job, or an agent that needs the exact
    values without re-deriving them.
    """
    import argparse
    import json

    from mangaeasy.brand import CLI_NAME

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} env",
        description="Print the environment that keeps every cache inside this "
                    "install folder. Source it before running uv directly.",
        epilog=f'Examples:\n  eval "$({CLI_NAME} env --sh)"\n'
               f"  {CLI_NAME} env --json\n"
               f"  for /f \"delims=\" %i in ('{CLI_NAME} env --bat') do @%i",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sh", action="store_const", const="sh", dest="shell",
                       help="Emit bash/zsh export lines (the default).")
    group.add_argument("--bat", action="store_const", const="bat", dest="shell",
                       help="Emit cmd.exe set lines.")
    group.add_argument("--ps1", action="store_const", const="ps1", dest="shell",
                       help="Emit PowerShell assignments.")
    group.add_argument("--json", action="store_true", dest="as_json",
                       help="Emit one JSON object: env, paths and isolation status.")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when anything would be written outside the "
                             "install folder (for CI and agents).")
    args = parser.parse_args()

    report = isolation_report()

    if args.as_json:
        print(json.dumps(
            {"env": {v: str(p) for v, p in cache_paths().items()},
             "behaviour": dict(BEHAVIOUR_ENV),
             **report},
            ensure_ascii=False,
        ))
    else:
        print(shell_exports(args.shell or "sh"), end="")

    if args.check and not report["isolated"]:
        for variable, value in report["escaping"].items():
            print(f"[error] {variable} points outside {report['install_root']}: {value}",
                  file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
