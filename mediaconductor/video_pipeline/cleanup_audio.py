from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from mediaconductor.brand import CLI_NAME
from mediaconductor.utils import LazyArchiveRunDir
from mediaconductor.video_pipeline.common import (
    DEFAULT_AUDIO_ROOT,
    DEFAULT_PROJECT_ROOT,
    item_dirs,
    merge_item_selection,
    project_name,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear generated audio from make_video/audio so it regenerates fresh, "
                     "without losing the previous take -- it's archived into old/run_NNNN/ "
                     f"first (see `{CLI_NAME} audio-takes-list`/`audio-takes-restore`)."
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item names or ranges, for example: 01 02 05-08.")
    parser.add_argument("--item-range", help="Convenience range, for example: 01-12.")
    parser.add_argument("--include-legacy", action="store_true", help="Also clear old item/audio folders if they exist.")
    parser.add_argument("--purge", action="store_true",
                         help="Permanently delete instead of archiving. Use this only if you really "
                              "don't want the previous take back -- audio is expensive to regenerate.")
    parser.add_argument("--yes", action="store_true", help="Actually clear. Default is dry run.")
    return parser.parse_args()


def safe_generated_audio_targets(args: argparse.Namespace) -> list[Path]:
    audio_root = args.audio_root.resolve()
    name = project_name(args.project_root, args.project_name)
    manga_audio = (audio_root / name).resolve()
    if manga_audio.parent != audio_root or manga_audio.name != name:
        raise ValueError(f"Refusing unsafe audio path: {manga_audio}")
    selected = merge_item_selection(args.items, args.item_range)
    if not selected:
        if not manga_audio.exists():
            return []
        if not manga_audio.is_dir():
            raise ValueError(f"Expected directory: {manga_audio}")
        return [manga_audio]

    # Selection accepts numeric equivalents ("1" and "01") everywhere else
    # in the pipeline. Resolve through the source item folders when they still
    # exist so cleanup targets the names generators actually used; fall back
    # to the explicit tokens so a stale combined WAV remains cleanable after
    # its source folder is gone.
    selected_dirs = item_dirs(args.project_root.resolve(), selected) if args.project_root.resolve().is_dir() else []
    selected_names: list[str] = []
    for name in [*(path.name for path in selected_dirs), *selected]:
        if name not in selected_names:
            selected_names.append(name)

    safe: list[Path] = []
    for chapter in selected_names:
        target = (manga_audio / chapter).resolve()
        if not target.exists():
            continue
        if not target.is_dir():
            raise ValueError(f"Expected directory: {target}")
        if target.parent != manga_audio:
            raise ValueError(f"Refusing to delete unsafe path: {target}")
        safe.append(target)

    combined_audio_root = (manga_audio / "_items").resolve()
    if combined_audio_root.parent != manga_audio:
        raise ValueError(f"Refusing unsafe combined audio folder: {combined_audio_root}")
    for chapter in selected_names:
        target = (combined_audio_root / f"item_{chapter}_narration.wav").resolve()
        if target.parent != combined_audio_root:
            raise ValueError(f"Refusing unsafe combined audio path: {target}")
        if not target.exists():
            continue
        if not target.is_file():
            raise ValueError(f"Expected combined audio file: {target}")
        safe.append(target)
    return safe


def safe_audio_dir(root: Path, chapter_dir: Path) -> Path | None:
    chapter_root = chapter_dir.resolve()
    audio_dir = (chapter_root / "audio").resolve()
    root = root.resolve()
    if not audio_dir.exists():
        return None
    if not audio_dir.is_dir():
        raise ValueError(f"Expected directory: {audio_dir}")
    if audio_dir.name.lower() != "audio" or audio_dir.parent != chapter_root or root not in audio_dir.parents:
        raise ValueError(f"Refusing to delete unsafe path: {audio_dir}")
    return audio_dir


def count_files(path: Path) -> int:
    if path.is_file():
        return 1
    return sum(1 for p in path.rglob("*") if p.is_file())


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    manga_audio = (args.audio_root.resolve() / project_name(args.project_root, args.project_name)).resolve()

    targets: list[tuple[Path, int, str]] = [
        (path, count_files(path), "_items" if path.is_file() else path.name)
        for path in safe_generated_audio_targets(args)
    ]
    if args.include_legacy:
        for chapter_dir in item_dirs(project_root, merge_item_selection(args.items, args.item_range)):
            audio_dir = safe_audio_dir(project_root, chapter_dir)
            if audio_dir:
                targets.append((audio_dir, count_files(audio_dir), f"legacy_{chapter_dir.name}"))

    # The whole-project target (no --items given) includes manga_audio's own
    # old/ archive folder as a child -- never sweep that into itself.
    targets = [(path, count, label) for path, count, label in targets if path.name != "old"]

    if not targets:
        print("No generated audio folders found.")
        return 0

    verb = "permanently delete" if args.purge else "archive (restorable later)"
    prefix = "Dry run, would" if not args.yes else "Will"
    print(f"{prefix} {verb} {len(targets)} audio target(s):")
    for audio_path, file_count, _ in targets:
        print(f"  {audio_path} ({file_count} file(s))")

    if not args.yes:
        print("\nRun again with --yes to apply.")
        return 0

    if args.purge:
        for audio_path, _, _ in targets:
            shutil.rmtree(audio_path) if audio_path.is_dir() else audio_path.unlink()
        print("\nPermanently deleted.")
        return 0

    archive_run_dir = LazyArchiveRunDir(manga_audio / "old")
    for audio_path, _, label in targets:
        destination = archive_run_dir.dir / label
        destination.mkdir(parents=True, exist_ok=True)
        if audio_path.is_file():
            child_destination = destination / audio_path.name
            if child_destination.exists():
                child_destination.unlink()
            shutil.move(str(audio_path), str(child_destination))
            continue

        # audio_path may be manga_audio itself (whole-project target) which
        # has the "old" archive folder as a child -- move its other children
        # individually rather than the directory itself, so "old" is never
        # swept into its own descendant.
        for child in audio_path.iterdir():
            if audio_path == manga_audio and child.name == "old":
                continue
            child_destination = destination / child.name
            if child_destination.exists():
                shutil.rmtree(child_destination) if child_destination.is_dir() else child_destination.unlink()
            shutil.move(str(child), str(child_destination))
        if audio_path != manga_audio:
            audio_path.rmdir()
    print(f"\nArchived to: {archive_run_dir.dir}")
    print(f"Pick it back up with `{CLI_NAME} audio-takes-restore`, or list takes with `{CLI_NAME} audio-takes-list`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
