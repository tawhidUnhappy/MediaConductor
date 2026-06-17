from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mangaeasy.runtime import popen_kwargs
from mangaeasy.tools.external import python_command, resolve_tool_dir, tool_env


def _normalize_project_args(args: list[str]) -> tuple[Path, list[str]]:
    project_root = Path.cwd().resolve()
    normalized: list[str] = []
    found = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--project-root" and index + 1 < len(args):
            project_root = Path(args[index + 1]).expanduser().resolve()
            normalized.extend(["--project-root", str(project_root)])
            found = True
            index += 2
            continue
        if arg.startswith("--project-root="):
            project_root = Path(arg.split("=", 1)[1]).expanduser().resolve()
            normalized.append(f"--project-root={project_root}")
            found = True
            index += 1
            continue
        normalized.append(arg)
        index += 1
    if not found:
        normalized = ["--project-root", str(project_root), *normalized]
    return project_root, normalized


def print_help() -> None:
    print("usage: mangaeasy got-ocr2 [options]")
    print()
    print("Run GOT-OCR 2.0 in its isolated env and write `ocr` fields to narration JSON files.")
    print()
    print("Common options:")
    print("  --project-root PATH      Folder to scan for narration.json / narration_*.json")
    print("  --items 01 02            Item folders to process")
    print("  --item-range 01-24       Item range to process")
    print("  --narration PATH [...]   Specific narration JSON file(s)")
    print("  --force                  Replace existing ocr fields")
    print("  --device auto|cuda|cpu   Inference device")
    print("  --batch-size N           Panels per OCR batch")
    print("  --formatted              Use GOT-OCR formatted mode")
    print("  --plain                  Compatibility flag; plain mode is the default")
    print("  --no-readability-breaks  Keep plain OCR output as one normalized string")
    print("  --only-images NAME [...] Only process matching narration image names")
    print()
    print("Install first with: mangaeasy install-tool got-ocr2")
    print("Environment overrides: GOT_OCR2_ROOT, GOT_OCR2_DIR, GOT_OCR_ROOT, GOT_OCR2_MODEL")


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print_help()
        return 0

    tool_dir = resolve_tool_dir("got-ocr2")
    assert tool_dir is not None

    script = Path(__file__).resolve().parents[1] / "ocr" / "got_ocr2_pipeline.py"
    project_root, args = _normalize_project_args(sys.argv[1:])

    env = tool_env()
    if "HF_HOME" not in os.environ:
        env["HF_HOME"] = str(project_root / ".hf_cache")
    if "HF_HUB_CACHE" not in os.environ:
        env["HF_HUB_CACHE"] = str(project_root / ".hf_cache" / "hub")
    env.setdefault("MANGAEASY_PROJECT_ROOT", str(project_root))
    env.setdefault("GOT_OCR2_ROOT", str(tool_dir))
    env.setdefault("GOT_OCR2_DIR", str(tool_dir))
    env.setdefault("GOT_OCR_ROOT", str(tool_dir))
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    command = [*python_command(tool_dir), str(script), *args]
    print(f"[tool:got-ocr2] {tool_dir}", flush=True)
    print(" ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=project_root if project_root.exists() else Path.cwd().resolve(),
        env=env,
        stderr=subprocess.STDOUT,
        **popen_kwargs(),
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
