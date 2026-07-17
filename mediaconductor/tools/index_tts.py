from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from mediaconductor.brand import CLI_NAME, PRODUCT_NAME
from mediaconductor.tools.external import python_command, resolve_tool_dir, tool_env
from mediaconductor import runtime


def print_help() -> None:
    print(f"usage: {CLI_NAME} index-tts --project-root <dir> --speaker-wav <wav> [args...]")
    print()
    print("Generate narration audio by delegating to the managed index-tts uv environment.")
    print("Arguments pass through to the batch pipeline (audio/tts_pipeline.py):")
    print("  --project-root DIR   (required)  --speaker-wav WAV  (required)")
    print("  --audio-root DIR  --project-name NAME  --items ...  --item-range A-B")
    print("  --overwrite  --resume  --emo-alpha F  --no-emotion")
    print(f"The command reads {PRODUCT_NAME} config.json/config.system.json from the current project root.")
    print()
    print("Environment overrides:")
    print("  INDEX_TTS_ROOT or INDEX_TTS_DIR")
    print("  MEDIACONDUCTOR_PROJECT_ROOT")


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print_help()
        return 0

    tool_dir = resolve_tool_dir("index-tts")
    assert tool_dir is not None

    # The batch pipeline script; audio/tts.py died with the GUI in 71dd592
    # but this launcher kept pointing at it, so `index-tts` always failed.
    script = Path(__file__).resolve().parents[1] / "audio" / "tts_pipeline.py"
    env = tool_env()
    env.setdefault("MEDIACONDUCTOR_PROJECT_ROOT", str(Path.cwd().resolve()))
    env.setdefault("INDEX_TTS_ROOT", str(tool_dir))
    env.setdefault("INDEX_TTS_DIR", str(tool_dir))
    # Force unbuffered output and UTF-8 so every print() line appears immediately
    # in the parent's log stream rather than arriving in one big flush at exit.
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    command = [*python_command(tool_dir), str(script), *sys.argv[1:]]
    print(f"[tool:index-tts] {tool_dir}", flush=True)
    print(" ".join(command), flush=True)
    # stderr=subprocess.STDOUT merges the grandchild's stderr into the same
    # stream as stdout so torchaudio/CUDA diagnostic messages reach the app log.
    return runtime.run(
        command, cwd=tool_dir, env=env,
        stderr=subprocess.STDOUT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
