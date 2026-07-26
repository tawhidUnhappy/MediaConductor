"""mediaconductor.qa_loop — the fix-until-clean loop and the reuse inventory.

``mediaconductor work-qa`` aggregates every *machine-checkable* quality gate for
the generated artifacts (crops present, OCR coverage, narration structure,
speakability, delivery safety, audio coverage + integrity, render freshness)
into one ordered problem list — each problem carrying a concrete ``fix``
command. That shape exists for small LLMs: the whole correction workflow
collapses to a loop a modest model can drive without global judgment —

    while mediaconductor work-qa ... --json reports problems:
        run the first problem's `fix`
        (re-narrate / narration-edit when the fix says so)

Exit codes make the machine loop trivial: 0 = machine-clean, 1 = problems
remain. Checks that need *eyes* (source page/strip overlays, crop sheets,
full-resolution panels, and narration review sheets) are surfaced as
``review`` items pointing at the exact files to read. ``ok`` means
machine-clean only; the JSON report separately states whether manual review
items remain. A vision pass, not another detector or OCR retry, resolves them.

``mediaconductor work-artifacts`` is the reuse inventory: everything expensive
this project has already generated (per-item videos, long-video takes,
archived audio runs, cached music beds, transcripts, QA sheets), each with
a hint for how to reuse it instead of regenerating.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mediaconductor.audio.narration_safety import narration_quality_findings
from mediaconductor.brand import CLI_NAME
from mediaconductor.video_pipeline.check_items import is_speakable
from mediaconductor.video_pipeline.common import (
    DEFAULT_AUDIO_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROJECT_ROOT,
    DEFAULT_WORK_DIR,
    item_dirs,
    merge_item_selection,
    project_name,
)
from mediaconductor.video_pipeline.item_assets import IMAGE_EXTENSIONS
from mediaconductor.video_pipeline.narration_check import check_item
from mediaconductor.workboard import _narration_entries as narration_entries_for_report
from mediaconductor.workboard import item_status

# Below this size a WAV cannot hold audible narration — it is a truncated or
# failed TTS write (the audible-audio deep check lives in video-audio-audit).
MIN_AUDIO_BYTES = 1024


def _stage_fix(stage: str, project_root: str, item: str) -> str:
    return {
        "download": f"{CLI_NAME} download --url <mangadex url> --name {Path(project_root).name} --chapters {item}",
        "crop": f"{CLI_NAME} page-split --project-root {project_root} --items {item}   (webtoon-split for vertical strips; then OPEN every overlay and full-resolution crop)",
        "transcribe": f"{CLI_NAME} panel-transcript --project-root {project_root} --items {item}",
        "narrate": f"write {project_root}/{item}/narration.json while viewing each original panel ({item}/transcript.json is optional, untrusted OCR cross-evidence; see mediaconductor/assets/prompts/narration.md), then re-run work-qa",
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

    # 1. Pipeline completeness — the loop's backbone: whatever stage is
    #    missing next is the first fix, in production order.
    stage = status["next_stage"]
    if stage in ("download", "crop", "transcribe"):
        detail = {
            "download": "no source pages downloaded",
            "crop": "no panels cropped yet",
            "transcribe": f"panel-transcript run started but incomplete ({status['transcript']['filled']}/{status['transcript']['total']}) — finish or delete transcript.json (OCR itself is optional)",
        }[stage]
        add("error", f"stage:{stage}", detail, _stage_fix(stage, root_arg, item))
        return problems  # later checks are meaningless before these exist

    if stage == "narrate":
        add("error", "stage:narrate", "no narration.json (or zero entries)",
            _stage_fix("narrate", root_arg, item))
        return problems

    # 2. Narration structure (dangling images, empty text, intro overlap...).
    report = check_item(item_dir)
    for problem in report["problems"]:
        add("error", "narration:structure", problem,
            f"{CLI_NAME} narration-edit --project-root {root_arg} --item {item} --list  "
            f"(then fix the entry with --set/--delete --prune-audio)")
    for warning in report.get("warnings", []):
        add("review", "narration:style", warning,
            f"{CLI_NAME} narration-review-sheets --project-root {root_arg} --items {item}, "
            "then OPEN every sheet and corresponding original crop before rewriting")

    # 3. Speakability and narration-quality lints, per entry.
    #    The tolerant reader is deliberate: a file with one dangling image
    #    still has 40 other lines worth linting, and reporting every problem
    #    in one pass is the whole point of the fix-until-clean loop.
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

    # 4. Audio coverage + integrity (cheap size gate; deep decode check is
    #    video-audio-audit).
    audio_dir = audio_root / name / item
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

    # 5. Render existence/freshness.
    if stage == "render":
        detail = "item video is stale (narration changed after render)" if status["render_stale"] \
            else "item video not rendered yet"
        add("error", "render:" + ("stale" if status["render_stale"] else "missing"), detail,
            _stage_fix("render", root_arg, item))

    # 6. Vision-required review artifacts. Machine checks cannot approve art.
    # Point at every evidence class, including paged overlays and webtoon's
    # actual flat output layout (not a nonexistent per-item subdirectory).
    page_verify = work_dir / "page_verify" / name / item
    webtoon_verify = work_dir / "webtoon_verify" / name
    crop_evidence: list[Path] = []
    if page_verify.is_dir():
        crop_evidence.extend(page_verify.glob(f"{item}_page_*.png"))
        crop_evidence.extend(page_verify.glob(f"{item}_sheet_*.png"))
    if webtoon_verify.is_dir():
        crop_evidence.extend(webtoon_verify.glob(f"{item}_strip_*.png"))
        crop_evidence.extend(webtoon_verify.glob(f"{item}_sheet_*.png"))
    cutcheck = work_dir / "cutcheck" / name
    if cutcheck.is_dir():
        crop_evidence.extend(cutcheck.glob(f"{item}_*.jpg"))
    crop_evidence = sorted({p.resolve() for p in crop_evidence})
    panels_dir = item_dir / "panels"
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
            f"{len(review_crops)} production crop(s) require a vision pass; "
            "open every overlay and every crop at readable resolution. MAGI/gutter output "
            "is not approval, and an automatic whole-page/strip stand-in is never acceptable.",
            f"Read {all_visual_evidence[0]} … compare against the original pages, fix every bad "
            "boundary/order/full-page result, re-split, and repeat the complete visual pass",
        )
    else:
        add(
            "review",
            "crop:review-artifacts-missing",
            "panels exist but no crop verification artifacts were found; manually inspect every "
            "original page and panel crop before narration or rendering",
            f"Run the correct splitter for {root_arg}/{item} to generate overlays/contact sheets, "
            "then open every result (or hand off to a vision-capable reviewer)",
        )

    narration_review = work_dir / "narration_review" / name / item
    narration_sheets = (
        sorted(p.resolve() for p in narration_review.glob("review_*.jpg"))
        if narration_review.is_dir() else []
    )
    if narration_sheets:
        add(
            "review",
            "narration:visual-review",
            f"{len(narration_sheets)} narration sheet(s) require comparison with the original "
            "full-resolution panels; OCR is an unverified hint, not source truth",
            f"Read {narration_sheets[0]} … open the original panel for EVERY line, fix each "
            "mismatch, regenerate the sheets, and review again",
        )
    else:
        add(
            "review",
            "narration:review-sheets-missing",
            "narration exists but semantic review sheets have not been generated",
            f"{CLI_NAME} narration-review-sheets --project-root {root_arg} --items {item} "
            f"--work-dir {work_dir}, then READ every sheet against the original panels",
        )
    return problems


def qa_main() -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} work-qa",
        description="Machine-checkable QA over crops, narration, audio and renders. Every "
                    "machine problem has a fix command; exit 0 does not waive the separately "
                    "reported manual visual reviews.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 05-08 (default: all).")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-22.")
    parser.add_argument("--max-problems", type=int, default=25,
                        help="Cap the list so it fits a small context window (default 25; 0 = all).")
    parser.add_argument("--errors-only", action="store_true",
                        help="Hide review/info items — only what blocks the build.")
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
            review_hint = (
                "rerun without --errors-only to list them"
                if args.errors_only
                else "open the listed source/crop/narration evidence"
            )
            print(
                f"REVIEW REQUIRED — {manual_reviews} visual review gate(s); "
                f"{review_hint} before production."
            )
    return 0 if errors == 0 else 1


# ── work-artifacts: what already exists and how to reuse it ─────────────────

def _dir_entry(path: Path, reuse: str, pattern: str = "*", recursive: bool = True) -> dict | None:
    if not path.is_dir():
        return None
    files = [p for p in (path.rglob(pattern) if recursive else path.glob(pattern)) if p.is_file()]
    if not files:
        return None
    return {"path": str(path), "files": len(files),
            "bytes": sum(p.stat().st_size for p in files), "reuse": reuse}


def artifacts_main() -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} work-artifacts",
        description="Inventory of every reusable generated artifact for a project — check here "
                    "before regenerating anything expensive.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = args.project_root
    if not root.is_dir():
        print(f"[ERROR] project root not found: {root}", file=sys.stderr)
        return 1
    name = project_name(root, args.project_name)

    categories = {
        "item_videos": _dir_entry(
            args.output_root / name / "items",
            "final per-item renders — video-join reuses them as-is; `video --skip-audio` re-renders only stale ones",
            "*.mp4", recursive=False),
        "item_video_archive": _dir_entry(
            args.output_root / name / "items" / "old",
            "archived earlier item renders (old/run_NNNN) — restorable by copying back"),
        "long_videos": _dir_entry(
            args.output_root / name,
            "joined long videos (timestamped, never clobbered) — video-add-bgm/video-normalize-audio "
            "rework these without re-joining", "*_full_*.mp4"),
        "output_archive": _dir_entry(
            args.output_root / name / "old",
            "archived earlier long-video takes (old/run_NNNN) — restorable by copying back"),
        "narration_audio": _dir_entry(
            args.audio_root / name,
            "generated TTS WAVs — any pipeline rerun without --overwrite-audio reuses them", "*.wav"),
        "audio_takes": _dir_entry(
            args.audio_root / name / "old",
            "archived audio takes — list with audio-takes-list, bring back with audio-takes-restore"),
        "transcripts": {
            "path": str(root), "files": sum(1 for d in item_dirs(root) if (d / "transcript.json").is_file()),
            "bytes": sum((d / "transcript.json").stat().st_size for d in item_dirs(root)
                         if (d / "transcript.json").is_file()),
            "reuse": "optional untrusted OCR cross-evidence — reuse only while each stored panel_sha256 matches",
        },
        "crop_verify_sheets": (_dir_entry(args.work_dir / "page_verify" / name,
                                          "crop QA sheets — re-READ after any re-split")
                               or _dir_entry(args.work_dir / "webtoon_verify" / name,
                                             "crop QA sheets — re-READ after any re-split")),
        "narration_review_sheets": _dir_entry(
            args.work_dir / "narration_review" / name,
            "panel+narration+OCR sheets — re-READ after narration edits"),
        "music_beds": _dir_entry(
            args.work_dir / "music_bed",
            "conditioned/looped BGM beds cached by content hash — video-add-bgm reuses them automatically",
            "*.flac"),
        "workboard": _dir_entry(
            root / ".workboard",
            "multi-agent claims + shared notes — see work-status / work-note"),
    }
    categories = {k: v for k, v in categories.items() if v and v["files"]}

    if args.as_json:
        print(json.dumps({"project": name, "artifacts": categories}, ensure_ascii=False))
        return 0
    if not categories:
        print("No generated artifacts yet.")
        return 0
    print(f"Reusable artifacts for {name}:")
    for key, info in categories.items():
        size_mb = info["bytes"] / 1_000_000
        print(f"  {key}: {info['files']} file(s), {size_mb:.1f} MB — {info['path']}")
        print(f"    reuse: {info['reuse']}")
    return 0
