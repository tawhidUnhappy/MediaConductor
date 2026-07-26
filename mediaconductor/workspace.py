"""Report — and check — every persistent path this install resolves.

The workspace is meant to be self-contained: source chapters, audio, renders,
review evidence, job state, tool environments, model caches and OAuth tokens
all live below one directory, so the whole production can be moved, backed up,
or deleted as a unit. Nothing enforced that. A stray ``MEDIACONDUCTOR_AUDIO_ROOT``,
a shared ``MEDIACONDUCTOR_HOME``, or simply running from the wrong cwd could scatter
gigabytes across the machine, and the first symptom was usually a second
``library/`` tree discovered weeks later.

``mediaconductor workspace-layout`` resolves every persistent root and reports
where it actually lands, which is also what ``doctor`` consumes to warn when a
root escapes the workspace. Roots are *reported*, never silently rewritten:
a deliberate override (a models cache on a second drive) is legitimate, and
the check exists to make it visible rather than to forbid it.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from mediaconductor.brand import CLI_NAME

# The recommended layout, documented in docs/manga-quality-design.md.
WORKSPACE_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("library", "source chapters and cropped panels"),
    ("audio", "raw TTS takes and provenance sidecars"),
    ("audio_faded", "render-safe narration derivatives"),
    ("output", "final and per-item videos"),
    ("review", "review evidence and reports"),
    ("work", "jobs, sheets, manifests, render scratch"),
    ("bgm", "user-owned licensed background music"),
    ("vocal", "user-owned narrator references"),
)

DATA_HOME_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("tools", "isolated AI tool environments"),
    ("cache", "Hugging Face, Torch, and uv model caches"),
    ("state", "workspace and runtime metadata"),
    ("secrets", "gitignored OAuth tokens"),
)


def _resolve(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def resolved_roots() -> dict[str, Path]:
    """Every persistent root this process would write to, already resolved."""
    from mediaconductor.config import PROJECT_ROOT
    from mediaconductor.jobs import jobs_dir
    from mediaconductor.tools.external import app_root, data_home, tools_home
    from mediaconductor.video_pipeline.common import (
        DEFAULT_AUDIO_ROOT,
        DEFAULT_OUTPUT_ROOT,
        DEFAULT_PROJECT_ROOT,
        DEFAULT_WORK_DIR,
    )
    from mediaconductor.youtube.store import youtube_dir

    roots: dict[str, Path] = {
        "app_root": _resolve(app_root()),
        "workspace_root": _resolve(PROJECT_ROOT),
        "data_home": _resolve(data_home()),
        "tools_home": _resolve(tools_home()),
        "items_root": _resolve(DEFAULT_PROJECT_ROOT),
        "audio_root": _resolve(DEFAULT_AUDIO_ROOT),
        "output_root": _resolve(DEFAULT_OUTPUT_ROOT),
        "work_dir": _resolve(DEFAULT_WORK_DIR),
        "jobs_dir": _resolve(jobs_dir()),
        "cache_home": _resolve(data_home() / "cache"),
        "state_home": _resolve(data_home() / "state"),
        "secrets_home": _resolve(youtube_dir()),
    }
    return roots


# Roots that genuinely belong to the workspace. ``app_root`` is the install
# itself and is allowed to sit elsewhere (a frozen build, a shared checkout).
_CONFINED_ROOTS = (
    "items_root", "audio_root", "output_root", "work_dir", "jobs_dir",
    "data_home", "tools_home", "cache_home", "state_home", "secrets_home",
)

_ROOT_ENV_OVERRIDES = {
    "items_root": ("MEDIACONDUCTOR_ITEMS_ROOT", "PROJECT_ROOT"),
    "audio_root": ("MEDIACONDUCTOR_AUDIO_ROOT", "AUDIO_ROOT"),
    "output_root": ("MEDIACONDUCTOR_OUTPUT_ROOT", "OUTPUT_ROOT"),
    "work_dir": ("MEDIACONDUCTOR_WORK_DIR", "WORK_DIR"),
    "jobs_dir": ("MEDIACONDUCTOR_JOBS_DIR",),
    "data_home": ("MEDIACONDUCTOR_HOME",),
    "tools_home": ("MEDIACONDUCTOR_TOOLS_DIR",),
    "workspace_root": ("MEDIACONDUCTOR_PROJECT_ROOT",),
    "app_root": ("MEDIACONDUCTOR_ROOT",),
}


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def layout_report() -> dict:
    """Resolved roots plus whether each stays inside the workspace."""
    roots = resolved_roots()
    workspace = roots["workspace_root"]
    entries: list[dict] = []
    escaped: list[str] = []
    for name, path in roots.items():
        confined = name in _CONFINED_ROOTS
        inside = _is_inside(path, workspace)
        overrides = {
            variable: os.environ.get(variable)
            for variable in _ROOT_ENV_OVERRIDES.get(name, ())
            if os.environ.get(variable)
        }
        entries.append({
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "inside_workspace": inside,
            "must_be_inside_workspace": confined,
            "env_overrides": overrides,
        })
        if confined and not inside:
            escaped.append(name)
    return {
        "ok": not escaped,
        "workspace_root": str(workspace),
        "roots": entries,
        "escaped_roots": escaped,
        "recommended_layout": {
            "workspace": {name: description for name, description in WORKSPACE_SUBDIRS},
            "data_home": {name: description for name, description in DATA_HOME_SUBDIRS},
        },
    }


def workspace_problems() -> list[str]:
    """Persistent roots resolving outside the workspace, as doctor messages."""
    report = layout_report()
    workspace = report["workspace_root"]
    problems: list[str] = []
    for entry in report["roots"]:
        if entry["name"] not in report["escaped_roots"]:
            continue
        override = ", ".join(f"{k}={v}" for k, v in entry["env_overrides"].items())
        hint = f" (set by {override})" if override else ""
        problems.append(
            f"{entry['name']} resolves to {entry['path']}, outside the workspace {workspace}"
            f"{hint}. Persistent production state should stay below the workspace so it can "
            "be moved, backed up, or deleted as one unit."
        )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} workspace-layout",
        description="Report every resolved persistent root and whether it stays inside "
                    "the workspace.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when any persistent root escapes the workspace.")
    args = parser.parse_args(argv)

    report = layout_report()
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] or not args.strict else 1

    print(f"workspace: {report['workspace_root']}\n")
    width = max(len(entry["name"]) for entry in report["roots"]) + 2
    for entry in report["roots"]:
        marker = " " if entry["inside_workspace"] or not entry["must_be_inside_workspace"] else "!"
        print(f" {marker} {entry['name']:<{width}}{entry['path']}")
    if report["escaped_roots"]:
        print()
        for problem in workspace_problems():
            print(f"  [warn] {problem}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
