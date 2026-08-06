"""mangaeasy.qa_loop — the fix-until-clean loop and the reuse inventory.

Updated with aspect ratio and gutter checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from mangaeasy.audio.narration_safety import narration_quality_findings
from mangaeasy.brand import CLI_NAME
from mangaeasy.video_pipeline.check_items import is_speakable
from mangaeasy.video_pipeline.common import (
    DEFAULT_AUDIO_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROJECT_ROOT,
    DEFAULT_WORK_DIR,
    item_dirs,
    merge_item_selection,
    project_name,
)
from mangaeasy.video_pipeline.item_assets import IMAGE_EXTENSIONS
from mangaeasy.video_pipeline.narration_check import check_item
from mangaeasy.workboard import _narration_entries as narration_entries_for_report
from mangaeasy.workboard import item_status

MIN_AUDIO_BYTES = 1024


def _stage_fix(stage: str, project_root: str, item: str) -> str:
    return {
        "download": f"{CLI_NAME} download --url <mangadex url> --name {Path(project_root).name} --chapters {item}",
        "crop": f"{CLI_NAME} page-split --project-root {project_root} --items {item}   (webtoon-split for vertical strips; then OPEN every overlay and full-resolution crop)",
        "transcribe": f"{CLI_NAME} panel-transcript --project-root {project_root} --items {item}",
        "narrate": f"write {project_root}/{item}/narration.json while viewing each original panel ({item}/transcript.json is optional, untrusted OCR cross-evidence; see mangaeasy/assets/prompts/narration.md), then re-run work-qa",
        "audio": f"{CLI_NAME} video --project-root {project_root} --items {item} --tts auto",
        "render": f"{CLI_NAME} video --project-root {project_root} --items {item} --skip-audio --overwrite-video",
    }[stage]


def qa_item(item_dir: Path, name: str, project_root: Path,
            audio_root: Path, output_root: Path, work_dir: Path) -> list[dict]:
    """Ordered problems for one item; empty list means machine-clean."""
    problems: list[dict] = []
    root_arg = str(project_root)
    item = item_dir.name

    def add(severity: str, kind: str, detail: str, fix: str) -> None:
        problems.append({"item": item, "severity": severity, "kind": kind,
                         "detail": detail, "fix": fix})

    status = item_status(item_dir, name, audio_root, output_root)

    # 1. Pipeline completeness
    stage = status["next_stage"]
    if stage in ("download", "crop", "transcribe"):
        detail = {
            "download": "no source pages downloaded",
            "crop": "no panels cropped yet",
            "transcribe": f"panel-transcript run started but incomplete ({status['transcript']['filled']}/{status['transcript']['total']}) — finish or delete transcript.json",
        }[stage]
        add("error", f"stage:{stage}", detail, _stage_fix(stage, root_arg, item))
        return problems

    if stage == "narrate":
        add("error", "stage:narrate", "no narration.json (or zero entries)",
            _stage_fix("narrate", root_arg, item))
        return problems

    # 1b. Crop Aspect Ratio & Gutter Check
    panels_dir = item_dir / "panels"
    if panels_dir.is_dir():
        for crop_path in panels_dir.glob("*.*"):
            if crop_path.suffix.lower() in IMAGE_EXTENSIONS:
                try:
                    with Image.open(crop_path) as img:
                        w, h = img.size
                        aspect = h / float(w) if w > 0 else 1.0
                        if aspect > 2.2 or aspect < 0.4:
                            add("error", "crop:bad_aspect_ratio",
                                f"{crop_path.name} aspect ratio is {aspect:.2f}:1 (limit 2.2:1 / 0.4:1). "
                                "Crop contains gutter whitespace or is too tall for 16:9.",
                                f"{CLI_NAME} webtoon-override --file work/overrides.json --item {item} --split-at <y>")
                except Exception:
                    pass

    # 2. Narration structure
    report = check_item(item_dir)
    for problem in report["problems"]:
        add("error", "narration:structure", problem,
            f"{CLI_NAME} narration-edit --project-root {root_arg} --item {item} --list  "
            f"(then fix the entry with --set/--delete --prune-audio)")
    for warning in report.get("warnings", []):
        add("review", "narration:style", warning,
            f"{CLI_NAME} narration-review-sheets --project-root {root_arg} --items {item}, "
            "then review risky entries first and sample clean entries before rewriting")

    # 3. Speakability and quality lints
    entries = narration_entries_for_report(item_dir)
    for entry in entries:
        image = entry.get("image") or "?"
        text = str(entry.get("narration") or "").strip()
        if text and not is_speakable(text):
            add("error", "narration:unspeakable",
                f"{image}: narration has no letters/digits (TTS emits near-silence): {text!r}",
                f"{CLI_NAME} narration-edit --project-root {root_arg} --item {item} "
                f"--set {image} \"<speakable line>\" --prune-audio")
    for finding in narration_quality_findings(entries):
        add("error" if finding.is_error else "review", f"narration:{finding.code}",
            f"{finding.beat}: {finding.message}",
            f"{CLI_NAME} narration-edit --project-root {root_arg} --item {item} "
            f"--set {finding.beat} \"<rewritten line>\" --prune-audio")

    # 4. Audio coverage
    audio_dir = audio_root / name / item if not audio_root.is_relative_to(project_root.resolve()) and audio_root != project_root.resolve() / "audio" else audio_root / item
    missing, corrupt = [], []
    for entry in entries:
        image = entry.get("image")
        if not image or not str(entry.get("narration") or "").strip():
            continue
        wav = audio_dir / f"{Path(image).stem}.wav"
        if not wav.is_file():
            missing.append(wav.name)
        elif wav.stat().st_size < MIN_AUDIO_BYTES:
            corrupt.append(wav.name)
    if missing:
        add("error", "audio:missing", f"{len(missing)} narration line(s) have no WAV: {', '.join(missing[:5])}…",
            _stage_fix("audio", root_arg, item))
    if corrupt:
        add("error", "audio:corrupt", f"{len(corrupt)} WAV(s) too small to be real audio: {', '.join(corrupt[:5])}",
            f"{CLI_NAME} video-audio-audit --project-root {root_arg} --items {item} --fix, then "
            + _stage_fix("audio", root_arg, item))

    # 5. Render freshness
    if stage == "render":
        detail = "item video is stale (narration changed after render)" if status["render_stale"] \
            else "item video not rendered yet"
        add("error", "render:" + ("stale" if status["render_stale"] else "missing"), detail,
            _stage_fix("render", root_arg, item))

    # 6. Vision-required review artifacts
    page_verify = (project_root / "work" / "page_verify" / item) if (project_root / "work" / "page_verify").is_dir() else (work_dir / "page_verify" / name / item if (work_dir / "page_verify" / name / item).is_dir() else work_dir / "page_verify" / item)
    webtoon_verify = (project_root / "work" / "webtoon_verify") if (project_root / "work" / "webtoon_verify").is_dir() else (work_dir / "webtoon_verify" / name if (work_dir / "webtoon_verify" / name).is_dir() else work_dir / "webtoon_verify")
    crop_evidence: list[Path] = []
    if page_verify.is_dir():
        crop_evidence.extend(page_verify.glob(f"{item}_page_*.png"))
        crop_evidence.extend(page_verify.glob(f"{item}_sheet_*.png"))
    if webtoon_verify.is_dir():
        crop_evidence.extend(webtoon_verify.glob(f"{item}_strip_*.png"))
        crop_evidence.extend(webtoon_verify.glob(f"{item}_sheet_*.png"))
    cutcheck = (project_root / "work" / "cutcheck") if (project_root / "work" / "cutcheck").is_dir() else (work_dir / "cutcheck" / name if (work_dir / "cutcheck" / name).is_dir() else work_dir / "cutcheck")
    if cutcheck.is_dir():
        crop_evidence.extend(cutcheck.glob(f"{item}_*.jpg"))
    crop_evidence = sorted({p.resolve() for p in crop_evidence})
    review_crops = sorted(
        path.resolve() for path in panels_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ) if panels_dir.is_dir() else []
    if crop_evidence:
        all_visual_evidence = sorted({*crop_evidence, *review_crops})
        add(
            "review",
            "crop:visual-review",
            f"{len(crop_evidence)} overlay/sheet/window image(s) and "
            f"{len(review_crops)} production crop(s) require a vision pass.",
            f"Read {all_visual_evidence[0]} … compare against original pages and re-split if needed",
        )
    else:
        add(
            "review",
            "crop:review-artifacts-missing",
            "panels exist but no crop verification artifacts were found",
            f"Run the correct splitter for {root_arg}/{item} to generate overlays",
        )

    narration_review = (project_root / "work" / "narration_review" / item) if (project_root / "work" / "narration_review").is_dir() else (work_dir / "narration_review" / name / item if (work_dir / "narration_review" / name / item).is_dir() else work_dir / "narration_review" / item)
    narration_sheets = (
        sorted(p.resolve() for p in narration_review.glob("review_*.jpg"))
        if narration_review.is_dir() else []
    )
    if narration_sheets:
        add(
            "review",
            "narration:visual-review",
            f"{len(narration_sheets)} narration sheet(s) require comparison with original panels",
            f"Read {narration_sheets[0]} … review OCR disagreements and speaker attribution",
        )
    else:
        add(
            "review",
            "narration:review-sheets-missing",
            "narration exists but semantic review sheets have not been generated",
            f"{CLI_NAME} narration-review-sheets --project-root {root_arg} --items {item} --work-dir {work_dir}",
        )
    return problems


def qa_main() -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} work-qa",
        description="Machine-checkable QA over crops, narration, audio and renders.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 05-08 (default: all).")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-22.")
    parser.add_argument("--max-problems", type=int, default=25)
    parser.add_argument("--errors-only", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = args.project_root
    if not root.is_dir():
        print(f"[ERROR] project root not found: {root}", file=sys.stderr)
        return 1
    name = project_name(root, args.project_name)
    selection = merge_item_selection(args.items, args.item_range)

    problems: list[dict] = []
    for item_dir in item_dirs(root, selection):
        problems.extend(qa_item(item_dir, name, root, args.audio_root, args.output_root, args.work_dir))

    manual_reviews = sum(1 for p in problems if p["severity"] == "review")
    if args.errors_only:
        problems = [p for p in problems if p["severity"] == "error"]
    errors = sum(1 for p in problems if p["severity"] == "error")
    total = len(problems)
    if args.max_problems:
        problems = problems[: args.max_problems]

    if args.as_json:
        print(json.dumps({
            "ok": errors == 0,
            "machine_ok": errors == 0,
            "review_required": manual_reviews > 0,
            "manual_review_required": manual_reviews > 0,
            "manual_reviews": manual_reviews,
            "errors": errors,
            "total_problems": total,
            "shown": len(problems),
            "problems": problems,
        }, ensure_ascii=False))
    else:
        if not problems:
            print("CLEAN — no machine-checkable problems.")
        for p in problems:
            print(f"[{p['severity'].upper()}] {p['item']} {p['kind']}: {p['detail']}")
            print(f"    fix: {p['fix']}")
        if total > len(problems):
            print(f"(+{total - len(problems)} more — fix these first, then re-run)")
        if manual_reviews:
            print(f"REVIEW REQUIRED — {manual_reviews} visual review gate(s) pending.")
    return 0 if errors == 0 else 1