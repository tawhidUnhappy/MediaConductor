"""Report — and check — every persistent path this install resolves.

The install keeps exactly two persistent trees (see
:mod:`mangaeasy.layout`): ``data/`` for everything downloaded or
generated, ``runtime/`` for tool envs, caches, state and secrets. The
promise that buys is concrete: **delete ``data/`` and the install is
factory-fresh**, with no second copy of a production hiding elsewhere.

Nothing enforced that before. A stray ``MANGAEASY_AUDIO_ROOT``, a
shared ``MANGAEASY_HOME``, or simply running from the wrong cwd could
scatter gigabytes across the machine, and the first symptom was usually a
second ``library/`` tree discovered weeks later.

``mangaeasy workspace-layout`` resolves every persistent root and
reports where it actually lands, which is also what ``doctor`` consumes to
warn when a root escapes. Roots are *reported*, never silently rewritten: a
deliberate override (a models cache on a second drive) is legitimate, and
the check exists to make it visible rather than to forbid it.

``mangaeasy workspace-reset`` is the supported way to take the fresh
start without opening a file manager — same outcome as deleting ``data/``,
but it refuses to run while a job is writing and it says what it removed.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from mangaeasy.brand import CLI_NAME
from mangaeasy.layout import DATA_SUBDIRS, RUNTIME_SUBDIRS
from mangaeasy.utils import remove_tree

# Kept as module attributes for callers that only want the workspace half.
WORKSPACE_SUBDIRS: tuple[tuple[str, str], ...] = DATA_SUBDIRS
DATA_HOME_SUBDIRS: tuple[tuple[str, str], ...] = RUNTIME_SUBDIRS

# User-owned folders that live beside data/ and must survive a reset: the
# user's licensed music and their narrator reference takes. mangaEasy
# reads them and never writes them, which is exactly why they are not in
# data/ — a fresh start must not cost someone their audio library.
USER_ASSET_DIRS: tuple[tuple[str, str], ...] = (
    ("bgm", "licensed background music"),
    ("vocal", "narrator reference takes"),
)


def _resolve(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def resolved_roots() -> dict[str, Path]:
    """Every persistent root this process would write to, already resolved."""
    from mangaeasy.config import PROJECT_ROOT
    from mangaeasy.jobs import jobs_dir
    from mangaeasy.layout import (
        cache_root,
        data_root,
        runtime_root,
        secrets_root,
        state_root,
    )
    from mangaeasy.tools.external import app_root, tools_home
    from mangaeasy.video_pipeline.common import (
        DEFAULT_AUDIO_ROOT,
        DEFAULT_OUTPUT_ROOT,
        DEFAULT_PROJECT_ROOT,
        DEFAULT_REVIEW_ROOT,
        DEFAULT_WORK_DIR,
    )

    return {
        "app_root": _resolve(app_root()),
        "workspace_root": _resolve(PROJECT_ROOT),
        "data_root": _resolve(data_root()),
        "items_root": _resolve(DEFAULT_PROJECT_ROOT),
        "audio_root": _resolve(DEFAULT_AUDIO_ROOT),
        "faded_audio_root": _resolve(Path(f"{DEFAULT_AUDIO_ROOT}_faded")),
        "output_root": _resolve(DEFAULT_OUTPUT_ROOT),
        "review_root": _resolve(DEFAULT_REVIEW_ROOT),
        "work_dir": _resolve(DEFAULT_WORK_DIR),
        "jobs_dir": _resolve(jobs_dir()),
        "runtime_home": _resolve(runtime_root()),
        "tools_home": _resolve(tools_home()),
        "cache_home": _resolve(cache_root()),
        "state_home": _resolve(state_root()),
        "secrets_home": _resolve(secrets_root()),
    }


# Roots holding downloaded/generated production state. Every one must sit
# inside data/, or "delete data/ to start fresh" is a lie.
_DATA_CONFINED_ROOTS = (
    "items_root", "audio_root", "faded_audio_root", "output_root",
    "review_root", "work_dir", "jobs_dir",
)

# Roots holding re-downloadable machinery and install state. These must sit
# inside runtime/ — and deliberately NOT inside data/, so a fresh start
# doesn't force an 80 GB re-download or a re-authorization.
_RUNTIME_CONFINED_ROOTS = ("tools_home", "cache_home", "state_home", "secrets_home")

_ROOT_ENV_OVERRIDES = {
    "items_root": ("MANGAEASY_ITEMS_ROOT",),
    "audio_root": ("MANGAEASY_AUDIO_ROOT",),
    "output_root": ("MANGAEASY_OUTPUT_ROOT",),
    "review_root": ("MANGAEASY_REVIEW_ROOT",),
    "work_dir": ("MANGAEASY_WORK_DIR",),
    "jobs_dir": ("MANGAEASY_JOBS_DIR",),
    "data_root": ("MANGAEASY_DATA_ROOT",),
    "runtime_home": ("MANGAEASY_HOME",),
    "tools_home": ("MANGAEASY_TOOLS_DIR",),
    "workspace_root": ("MANGAEASY_PROJECT_ROOT",),
    "app_root": ("MANGAEASY_ROOT",),
}


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def layout_report() -> dict:
    """Resolved roots plus whether each one landed where it belongs."""
    roots = resolved_roots()
    workspace = roots["workspace_root"]
    data = roots["data_root"]
    runtime = roots["runtime_home"]

    entries: list[dict] = []
    escaped: list[str] = []
    for name, path in roots.items():
        if name in _DATA_CONFINED_ROOTS:
            container, inside = "data_root", _is_inside(path, data)
        elif name in _RUNTIME_CONFINED_ROOTS:
            container, inside = "runtime_home", _is_inside(path, runtime)
        elif name == "data_root":
            container, inside = "workspace_root", _is_inside(path, workspace)
        else:
            container, inside = None, True
        overrides = {
            variable: os.environ.get(variable)
            for variable in _ROOT_ENV_OVERRIDES.get(name, ())
            if os.environ.get(variable)
        }
        entries.append({
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "must_be_inside": container,
            "contained": inside,
            "env_overrides": overrides,
        })
        if container is not None and not inside:
            escaped.append(name)

    # data/ inside runtime/ (or the reverse) would make a reset delete the
    # tool envs, or make deleting data/ miss half the production.
    overlapping = _is_inside(data, runtime) or _is_inside(runtime, data)
    return {
        "ok": not escaped and not overlapping,
        "workspace_root": str(workspace),
        "data_root": str(data),
        "runtime_home": str(runtime),
        "roots": entries,
        "escaped_roots": escaped,
        "data_runtime_overlap": overlapping,
        "fresh_start": {
            "delete": str(data),
            "command": f"{CLI_NAME} workspace-reset",
            "survives": [str(runtime), *(
                str(workspace / name) for name, _ in USER_ASSET_DIRS
            )],
        },
        "recommended_layout": {
            "data": {name: description for name, description in DATA_SUBDIRS},
            "runtime": {name: description for name, description in RUNTIME_SUBDIRS},
            "user_assets": {name: description for name, description in USER_ASSET_DIRS},
        },
    }


def workspace_problems() -> list[str]:
    """Persistent roots resolving outside their tree, as doctor messages."""
    report = layout_report()
    problems: list[str] = []
    for entry in report["roots"]:
        if entry["name"] not in report["escaped_roots"]:
            continue
        override = ", ".join(f"{k}={v}" for k, v in entry["env_overrides"].items())
        hint = f" (set by {override})" if override else ""
        container = report[entry["must_be_inside"]]
        problems.append(
            f"{entry['name']} resolves to {entry['path']}, outside {container}{hint}. "
            f"Production state must stay under data/ so deleting that one folder "
            f"really is a fresh start; machinery must stay under runtime/ so a fresh "
            f"start doesn't re-download it."
        )
    if report["data_runtime_overlap"]:
        problems.append(
            f"data_root ({report['data_root']}) and runtime_home "
            f"({report['runtime_home']}) overlap: a workspace reset would delete the "
            f"installed AI tool environments, and deleting data/ would not be a clean "
            f"fresh start. Point MANGAEASY_HOME or MANGAEASY_DATA_ROOT apart."
        )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} workspace-layout",
        description="Report every resolved persistent root and whether it stays in "
                    "the tree it belongs to (data/ for production, runtime/ for tools).",
    )
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when any persistent root lands outside its tree.")
    args = parser.parse_args(argv)

    report = layout_report()
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] or not args.strict else 1

    print(f"workspace: {report['workspace_root']}\n")
    width = max(len(entry["name"]) for entry in report["roots"]) + 2
    for entry in report["roots"]:
        marker = " " if entry["contained"] else "!"
        print(f" {marker} {entry['name']:<{width}}{entry['path']}")
    print(f"\n  fresh start: delete {report['data_root']}  (or run "
          f"{CLI_NAME} workspace-reset)")
    print(f"  survives:    {report['runtime_home']}, "
          + ", ".join(name for name, _ in USER_ASSET_DIRS))
    if not report["ok"]:
        print()
        for problem in workspace_problems():
            print(f"  [warn] {problem}")
    return 0 if report["ok"] or not args.strict else 1


# ── workspace-reset ───────────────────────────────────────────────────────────

def _dir_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def reset_main(argv: Sequence[str] | None = None) -> int:
    """Clear generated/downloaded state — the scriptable 'delete data/'."""
    from mangaeasy.jobs import live_jobs
    from mangaeasy.layout import data_root, ensure_data_root
    from mangaeasy.utils import emit_result

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} workspace-reset",
        description="Delete everything mangaEasy downloaded or generated "
                    "(the data/ folder) and recreate it empty. Installed AI tools, "
                    "caches, YouTube tokens, bgm/ and vocal/ are untouched.",
    )
    parser.add_argument("--confirm", action="store_true",
                        help="Actually delete. Without it this is a dry run.")
    parser.add_argument("--keep-library", action="store_true",
                        help="Keep data/library/ (downloaded chapters and panels) and "
                             "clear only what can be regenerated from it.")
    parser.add_argument("--only", nargs="*", metavar="SUBDIR",
                        help="Clear only these data/ subfolders "
                             f"({', '.join(name for name, _ in DATA_SUBDIRS)}).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args(argv)

    known = [name for name, _ in DATA_SUBDIRS]
    if args.only:
        unknown = sorted(set(args.only) - set(known))
        if unknown:
            parser.error(f"unknown data subfolder(s): {', '.join(unknown)}; "
                         f"known: {', '.join(known)}")
        targets = [name for name in known if name in set(args.only)]
    elif args.keep_library:
        targets = [name for name in known if name != "library"]
    else:
        targets = known

    # A render writing into a tree being deleted produces a half-erased
    # production and a confusing traceback instead of a clean refusal.
    running = live_jobs()
    if running and args.confirm:
        detail = ", ".join(f"{job['id']} ({job['command']})" for job in running)
        message = (f"refusing to reset while {len(running)} job(s) are running: {detail}. "
                   f"Wait for them, or stop them, then retry.")
        if args.as_json:
            print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        else:
            print(f"[error] {message}")
        return 1

    root = data_root()
    removed: list[dict] = []
    for name in targets:
        path = root / name
        if not path.exists():
            continue
        size = _dir_size(path)
        entry = {"path": str(path), "bytes": size, "human": _human(size)}
        if args.confirm:
            remove_tree(path)
        removed.append(entry)

    if args.confirm:
        ensure_data_root()

    total = sum(entry["bytes"] for entry in removed)
    payload = {
        "ok": True,
        "dry_run": not args.confirm,
        "data_root": str(root),
        "cleared": removed,
        "kept": sorted(set(known) - set(targets)),
        "freed_bytes": total,
        "freed": _human(total),
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if not removed:
            print(f"[reset] nothing to clear under {root}")
        for entry in removed:
            verb = "removed" if args.confirm else "would remove"
            print(f"  {verb} {entry['path']}  ({entry['human']})")
        if payload["kept"]:
            print(f"  kept: {', '.join(payload['kept'])}")
        print(f"\n{'Freed' if args.confirm else 'Would free'} {payload['freed']}. "
              f"Installed tools, caches, YouTube tokens, bgm/ and vocal/ are untouched.")
        if not args.confirm:
            print(f"Re-run with --confirm to delete: {CLI_NAME} workspace-reset --confirm")
    emit_result(**payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
