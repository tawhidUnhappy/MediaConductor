"""Durable, content-bound review records for the manga production pipeline.

Updated with reading-sheet pre-requisite enforcement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mangaeasy.brand import CLI_NAME
from mangaeasy.path_safety import relative_subpath_arg, validate_relative_subpath

SCHEMA_VERSION = 1
REVIEW_RECORD_RELATIVE_PATH = Path(".mangaeasy") / "manga-reviews.json"
LEGACY_REVIEW_RECORD_RELATIVE_PATH = Path(".mediaconductor") / "manga-reviews.json"


class ReviewRecordError(ValueError):
    """A review cannot be recorded or is not current for the requested build."""


def review_record_path(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / REVIEW_RECORD_RELATIVE_PATH


def legacy_review_record_path(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / LEGACY_REVIEW_RECORD_RELATIVE_PATH


def existing_review_record_path(project_root: Path) -> Path:
    current = review_record_path(project_root)
    if current.is_file():
        return current
    legacy = legacy_review_record_path(project_root)
    return legacy if legacy.is_file() else current


def _empty_store() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "crop": {},
        "narration": {},
        "final_video": None,
    }


def load_review_store(project_root: Path) -> dict:
    path = existing_review_record_path(project_root)
    if not path.is_file():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReviewRecordError(f"could not read manga review records at {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ReviewRecordError(
            f"unsupported manga review record schema at {path}; "
            f"expected schema_version {SCHEMA_VERSION}"
        )
    for stage in ("crop", "narration"):
        if not isinstance(data.get(stage), dict):
            raise ReviewRecordError(f"manga review record field '{stage}' must be an object")
    if data.get("final_video") is not None and not isinstance(data["final_video"], dict):
        raise ReviewRecordError("manga review record field 'final_video' must be an object or null")
    return data


def _write_review_store(project_root: Path, store: dict) -> Path:
    path = review_record_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    payload = json.dumps(
        store,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _file_entry(path: Path, relative_to: Path) -> dict:
    digest, size = sha256_file(path)
    try:
        displayed = path.relative_to(relative_to).as_posix()
    except ValueError:
        displayed = str(path.resolve())
    return {"path": displayed, "sha256": digest, "size": size}


def snapshot_files(
    root: Path,
    *,
    relative_to: Path,
    label: str,
    required: bool = True,
) -> dict:
    root = Path(root)
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    ) if root.is_dir() else []
    if required and not paths:
        raise ReviewRecordError(f"{label} has no files to review: {root}")
    files = [_file_entry(path, relative_to) for path in paths]
    return {
        "digest": _canonical_digest({"files": files}),
        "files": files,
    }


def crop_input_snapshot(
    item_dir: Path,
    *,
    source_subdir: str = "download",
    panels_subdir: str = "panels",
) -> dict:
    source_subdir = validate_relative_subpath(source_subdir, label="source subdirectory")
    panels_subdir = validate_relative_subpath(panels_subdir, label="panels subdirectory")
    item_dir = Path(item_dir).resolve()
    sources = snapshot_files(
        item_dir / source_subdir,
        relative_to=item_dir,
        label=f"{item_dir.name} source input",
    )
    panels = snapshot_files(
        item_dir / panels_subdir,
        relative_to=item_dir,
        label=f"{item_dir.name} panel crops",
    )
    basis = {
        "item": item_dir.name,
        "source_subdir": source_subdir,
        "panels_subdir": panels_subdir,
        "sources": sources,
        "panels": panels,
    }
    return {**basis, "input_digest": _canonical_digest(basis)}


def narration_input_snapshot(
    item_dir: Path,
    *,
    panels_subdir: str = "panels",
) -> dict:
    """Snapshot current panels plus narration.json/intro.json after verifying reading sheets."""
    panels_subdir = validate_relative_subpath(panels_subdir, label="panels subdirectory")
    item_dir = Path(item_dir).resolve()

    # Pre-requisite check: verify panel-reading-sheets were generated
    work_dir = item_dir.parent.parent / "work" / "panel_reading" / item_dir.parent.name / item_dir.name
    if not work_dir.is_dir() or not list(work_dir.glob("*.jpg")):
        raise ReviewRecordError(
            f"Narration review blocked for {item_dir.name}: Panel reading sheets missing under {work_dir}. "
            f"Run '{CLI_NAME} panel-reading-sheets --items {item_dir.name}' and inspect them before reviewing narration."
        )

    narration_path = item_dir / "narration.json"
    if not narration_path.is_file():
        raise ReviewRecordError(f"{item_dir.name} narration is missing: {narration_path}")
    script_paths = [narration_path]
    intro_path = item_dir / "intro.json"
    if intro_path.is_file():
        script_paths.append(intro_path)
    scripts = [_file_entry(path, item_dir) for path in script_paths]
    script_snapshot = {
        "digest": _canonical_digest({"files": scripts}),
        "files": scripts,
    }
    panels = snapshot_files(
        item_dir / panels_subdir,
        relative_to=item_dir,
        label=f"{item_dir.name} narration panels",
    )
    basis = {
        "item": item_dir.name,
        "panels_subdir": panels_subdir,
        "panels": panels,
        "scripts": script_snapshot,
    }
    return {**basis, "input_digest": _canonical_digest(basis)}


def _reviewer(value: str) -> str:
    reviewer = str(value or "").strip()
    if not reviewer:
        raise ReviewRecordError("reviewer must be a non-empty name or agent identity")
    if len(reviewer) > 200:
        raise ReviewRecordError("reviewer must be 200 characters or fewer")
    return reviewer


def _timestamp(value: str | None) -> str:
    timestamp = str(value or "").strip()
    if timestamp:
        return timestamp
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _selected_item_dirs(project_root: Path, items: Sequence[str] | None) -> list[Path]:
    from mangaeasy.video_pipeline.common import item_dirs

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ReviewRecordError(f"project root does not exist: {root}")
    selected = item_dirs(root, list(items) if items else None)
    if not selected:
        raise ReviewRecordError(f"no manga items selected under {root}")
    return selected


def _record_stage(
    stage: str,
    project_root: Path,
    items: Sequence[str] | None,
    *,
    reviewer: str,
    reviewed_at: str | None,
    source_subdir: str = "download",
) -> dict:
    if stage not in {"crop", "narration"}:
        raise ReviewRecordError(f"unsupported review stage: {stage}")
    root = Path(project_root).expanduser().resolve()
    selected = _selected_item_dirs(root, items)
    reviewer = _reviewer(reviewer)
    reviewed_at = _timestamp(reviewed_at)
    snapshots: dict[str, dict] = {}
    for item_dir in selected:
        if stage == "crop":
            snapshots[item_dir.name] = crop_input_snapshot(
                item_dir,
                source_subdir=source_subdir,
            )
        else:
            snapshots[item_dir.name] = narration_input_snapshot(item_dir)

    store = load_review_store(root)
    records = dict(store[stage])
    for item, snapshot in snapshots.items():
        records[item] = {
            "reviewed_at": reviewed_at,
            "reviewer": reviewer,
            **snapshot,
        }
    store[stage] = records
    path = _write_review_store(root, store)
    return {
        "ok": True,
        "stage": stage,
        "record_file": str(path),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "items": sorted(snapshots),
        "input_digests": {
            item: snapshots[item]["input_digest"]
            for item in sorted(snapshots)
        },
    }


def record_crop_review(
    project_root: Path,
    items: Sequence[str] | None,
    *,
    reviewer: str,
    reviewed_at: str | None = None,
    source_subdir: str = "download",
) -> dict:
    return _record_stage(
        "crop",
        project_root,
        items,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        source_subdir=source_subdir,
    )


def record_narration_review(
    project_root: Path,
    items: Sequence[str] | None,
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict:
    return _record_stage(
        "narration",
        project_root,
        items,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
    )


def _check_stage(
    stage: str,
    project_root: Path,
    selected: Sequence[Path],
    store: dict,
) -> dict:
    item_reports: dict[str, dict] = {}
    for item_dir in selected:
        record = store[stage].get(item_dir.name)
        if not isinstance(record, dict):
            item_reports[item_dir.name] = {
                "ok": False,
                "status": "missing",
                "detail": f"no {stage} review has been recorded",
            }
            continue
        try:
            if stage == "crop":
                current = crop_input_snapshot(
                    item_dir,
                    source_subdir=record.get("source_subdir", "download"),
                    panels_subdir=record.get("panels_subdir", "panels"),
                )
            else:
                current = narration_input_snapshot(
                    item_dir,
                    panels_subdir=record.get("panels_subdir", "panels"),
                )
        except (OSError, ReviewRecordError, ValueError) as exc:
            item_reports[item_dir.name] = {
                "ok": False,
                "status": "stale",
                "recorded_digest": record.get("input_digest"),
                "detail": str(exc),
            }
            continue
        recorded_digest = record.get("input_digest")
        current_digest = current["input_digest"]
        current_ok = recorded_digest == current_digest
        item_reports[item_dir.name] = {
            "ok": current_ok,
            "status": "current" if current_ok else "stale",
            "reviewer": record.get("reviewer"),
            "reviewed_at": record.get("reviewed_at"),
            "recorded_digest": recorded_digest,
            "current_digest": current_digest,
            "detail": (
                "review matches current inputs"
                if current_ok
                else f"{stage} inputs changed after review"
            ),
        }
    return {
        "ok": all(report["ok"] for report in item_reports.values()),
        "items": item_reports,
    }


def record_final_video_review(
    project_root: Path,
    video: Path,
    items: Sequence[str] | None,
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict:
    root = Path(project_root).expanduser().resolve()
    selected = _selected_item_dirs(root, items)
    prior = check_review_records(
        root,
        [item.name for item in selected],
        stages=("crop", "narration"),
    )
    if not prior["ok"]:
        raise ReviewRecordError(
            "cannot record final video review while crop/narration approvals are missing or stale:\n"
            + "\n".join(f"  - {problem}" for problem in prior["problems"])
        )
    video = Path(video).expanduser().resolve()
    if not video.is_file() or video.suffix.casefold() != ".mp4":
        raise ReviewRecordError(f"final video must be an existing MP4: {video}")
    video_digest, video_size = sha256_file(video)
    reviewer = _reviewer(reviewer)
    reviewed_at = _timestamp(reviewed_at)
    store = load_review_store(root)
    item_inputs = {
        item.name: {
            "crop_input_digest": store["crop"][item.name]["input_digest"],
            "narration_input_digest": store["narration"][item.name]["input_digest"],
        }
        for item in selected
    }
    basis = {
        "items": [item.name for item in selected],
        "item_inputs": item_inputs,
        "video": {
            "path": video.relative_to(root).as_posix() if video.is_relative_to(root) else str(video),
            "sha256": video_digest,
            "size": video_size,
        },
    }
    store["final_video"] = {
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        **basis,
        "input_digest": _canonical_digest(basis),
    }
    path = _write_review_store(root, store)
    return {
        "ok": True,
        "stage": "final_video",
        "record_file": str(path),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "items": basis["items"],
        "video": basis["video"],
        "input_digest": store["final_video"]["input_digest"],
    }


def check_review_records(
    project_root: Path,
    items: Sequence[str] | None,
    *,
    stages: Sequence[str] = ("crop", "narration"),
    video: Path | None = None,
) -> dict:
    root = Path(project_root).expanduser().resolve()
    selected = _selected_item_dirs(root, items)
    store = load_review_store(root)
    reports: dict[str, dict] = {}
    for stage in stages:
        if stage in {"crop", "narration"}:
            reports[stage] = _check_stage(stage, root, selected, store)
    problems: list[str] = []
    for stage, report in reports.items():
        for item, item_report in report["items"].items():
            if not item_report["ok"]:
                problems.append(f"{stage} {item}: {item_report['detail']}")
    return {
        "ok": not problems,
        "project_root": str(root),
        "record_file": str(existing_review_record_path(root)),
        "items": [item.name for item in selected],
        "stages": reports,
        "problems": problems,
    }


def enforce_production_reviews(
    project_root: Path,
    items: Sequence[str] | None,
    *,
    stage: str = "TTS/render",
) -> dict:
    report = check_review_records(
        project_root,
        items,
        stages=("crop", "narration"),
    )
    if report["ok"]:
        return report
    detail = "\n".join(f"  - {problem}" for problem in report["problems"])
    raise ReviewRecordError(
        f"manga production review gate failed before {stage}:\n"
        f"{detail}\n"
        f"Record current reviews with `{CLI_NAME} manga-review crop ...` and "
        f"`{CLI_NAME} manga-review narration ...` after completing the visual passes."
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} manga-review",
        description="Record/check hash-bound manga crop, narration, and final-video reviews.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    crop = subparsers.add_parser("crop", help="Approve exact source files and panel crops.")
    crop.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    crop.add_argument("--items", nargs="*")
    crop.add_argument("--item-range")
    crop.add_argument("--reviewer", required=True)
    crop.add_argument("--reviewed-at", default=None)
    crop.add_argument("--source-subdir", type=relative_subpath_arg, default="download")

    narration = subparsers.add_parser("narration", help="Approve exact panels plus narration.json.")
    narration.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    narration.add_argument("--items", nargs="*")
    narration.add_argument("--item-range")
    narration.add_argument("--reviewer", required=True)
    narration.add_argument("--reviewed-at", default=None)

    final = subparsers.add_parser("final-video", help="Approve final MP4.")
    final.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    final.add_argument("--items", nargs="*")
    final.add_argument("--item-range")
    final.add_argument("--video", type=Path, required=True)
    final.add_argument("--reviewer", required=True)
    final.add_argument("--reviewed-at", default=None)

    check = subparsers.add_parser("check", help="Check review currency.")
    check.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    check.add_argument("--items", nargs="*")
    check.add_argument("--item-range")
    check.add_argument("--stage", action="append", choices=("crop", "narration", "final_video"), dest="stages")
    check.add_argument("--video", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    from mangaeasy.video_pipeline.common import merge_item_selection

    args = parse_args(argv)
    items = merge_item_selection(getattr(args, "items", None), getattr(args, "item_range", None))
    try:
        if args.action == "crop":
            report = record_crop_review(
                args.project_root, items, reviewer=args.reviewer,
                reviewed_at=args.reviewed_at, source_subdir=args.source_subdir,
            )
        elif args.action == "narration":
            report = record_narration_review(
                args.project_root, items, reviewer=args.reviewer, reviewed_at=args.reviewed_at,
            )
        elif args.action == "final-video":
            report = record_final_video_review(
                args.project_root, args.video, items, reviewer=args.reviewer, reviewed_at=args.reviewed_at,
            )
        else:
            report = check_review_records(
                args.project_root, items, stages=tuple(args.stages or ("crop", "narration")), video=args.video,
            )
    except ReviewRecordError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())