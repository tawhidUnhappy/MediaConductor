"""mangaeasy.images.sheets_zip — pack generated reading/review sheets into split ZIPs (<= 1 GB each)."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Callable

from mangaeasy.brand import CLI_NAME
from mangaeasy.layout import ensure_data_root, zips_root
from mangaeasy.utils import emit_result

MAX_ZIP_BYTES = 1000 * 1024 * 1024  # 1 GB
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def pack_sheets_to_zips(
    project_root: Path,
    out_dir: Path | None = None,
    max_bytes: int = MAX_ZIP_BYTES,
    log: Callable[[str], None] = print,
) -> list[Path]:
    project_root = project_root.resolve()
    ensure_data_root(project_root=project_root)
    output_directory = (out_dir or zips_root(project_root)).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    from mangaeasy.layout import data_root
    global_data_root = data_root().resolve()

    search_dirs = [
        project_root / "review",
        project_root / "work",
        global_data_root / "work" / "panel_reading" / project_root.name,
        global_data_root / "work" / "narration_review" / project_root.name,
        global_data_root / "work" / "webtoon_verify" / project_root.name,
        global_data_root / "work" / "page_verify" / project_root.name,
        global_data_root / "work" / "cutcheck" / project_root.name,
        global_data_root / "review" / project_root.name,
    ]

    files: list[Path] = []
    for s_dir in search_dirs:
        if s_dir.is_dir():
            for p in sorted(s_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and p not in files:
                    files.append(p)

    if not files:
        log(f"[sheets-zip] No generated sheet images found for {project_root.name}.")
        return []

    created_zips: list[Path] = []
    volume_index = 1
    current_zip_bytes = 0
    current_zip_path = output_directory / f"sheets_part_{volume_index:02d}.zip"
    current_zip = zipfile.ZipFile(current_zip_path, "w", compression=zipfile.ZIP_STORED)

    for file_path in files:
        file_size = file_path.stat().st_size
        if current_zip_bytes + file_size > max_bytes and current_zip_bytes > 0:
            current_zip.close()
            created_zips.append(current_zip_path)
            log(f"[sheets-zip] Finalized volume {current_zip_path.name} ({current_zip_bytes / (1024*1024):.1f} MB)")
            volume_index += 1
            current_zip_path = output_directory / f"sheets_part_{volume_index:02d}.zip"
            current_zip = zipfile.ZipFile(current_zip_path, "w", compression=zipfile.ZIP_STORED)
            current_zip_bytes = 0

        try:
            arcname = file_path.relative_to(project_root).as_posix()
        except ValueError:
            arcname = file_path.name
        current_zip.write(file_path, arcname=arcname)
        current_zip_bytes += file_size

    if current_zip_bytes > 0:
        current_zip.close()
        created_zips.append(current_zip_path)
        log(f"[sheets-zip] Finalized volume {current_zip_path.name} ({current_zip_bytes / (1024*1024):.1f} MB)")

    log(f"[sheets-zip] Packed {len(files)} sheet(s) into {len(created_zips)} archive(s) <= 1 GB under {output_directory}")
    return created_zips


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} sheets-pack",
        description="Pack generated reading and review sheets into split ZIP files <= 1 GB stored in <project_root>/zips/.",
    )
    parser.add_argument("--project-root", type=Path, required=True, help="Path to manga project directory.")
    parser.add_argument("--max-size-mb", type=int, default=1000, help="Maximum ZIP size in MB (default: 1000 MB).")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    max_bytes = args.max_size_mb * 1024 * 1024
    created_zips = pack_sheets_to_zips(args.project_root, args.out_dir, max_bytes=max_bytes)

    result = {
        "ok": True,
        "project_root": str(args.project_root.resolve()),
        "zips": [str(z) for z in created_zips],
        "count": len(created_zips),
    }
    emit_result(**result)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())