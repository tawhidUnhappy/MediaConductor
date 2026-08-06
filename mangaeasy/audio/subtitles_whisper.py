"""mangaeasy.audio.subtitles_whisper — Subtitle generation via Whisper large-v3-turbo.

Runs faster-whisper with `deepdml/faster-whisper-large-v3-turbo-ct2` (or HuggingFace repo ID)
to generate word-level timestamped `.ass` and `.srt` subtitle files in `<project_root>/subtitles/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mangaeasy import runtime
from mangaeasy.brand import CLI_NAME
from mangaeasy.layout import subtitles_root
from mangaeasy.tools.external import python_command, resolve_tool_dir, tool_env
from mangaeasy.utils import emit_result

MODEL_HF_REPO = "deepdml/faster-whisper-large-v3-turbo-ct2"


def _fmt_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_subtitles_in_env(
    audio_video_file: Path,
    out_ass: Path,
    out_srt: Path,
    model_repo: str = MODEL_HF_REPO,
    device: str = "cuda",
) -> tuple[Path, Path]:
    tool_dir = resolve_tool_dir("whisper-turbo", required=False)
    if tool_dir is None:
        raise RuntimeError("whisper-turbo tool environment not installed. Run `mangaeasy install-tool whisper-turbo` first.")

    out_ass.parent.mkdir(parents=True, exist_ok=True)
    worker_script = Path(__file__).resolve().parent / "_whisper_worker.py"
    
    # Write worker inline script if missing
    if not worker_script.is_file():
        worker_code = """
import sys, json
from pathlib import Path
from faster_whisper import WhisperModel

audio_path = Path(sys.argv[1])
out_ass = Path(sys.argv[2])
out_srt = Path(sys.argv[3])
model_repo = sys.argv[4]
device = sys.argv[5]

compute_type = "float16" if device == "cuda" else "int8"
model = WhisperModel(model_repo, device=device, compute_type=compute_type)

segments, info = model.transcribe(str(audio_path), beam_size=5, word_timestamps=True)
seg_list = list(segments)

# Write ASS
ass_header = (
    "[Script Info]\\nScriptType: v4.00+\\nPlayResX: 1920\\nPlayResY: 1080\\n\\n"
    "[V4+ Styles]\\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
    "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\\n"
    "Style: Default,Arial,48,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,50,1\\n\\n"
    "[Events]\\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\\n"
)

def fmt_ass(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); cs = int(round((s % 1) * 100))
    if cs >= 100: cs = 99
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"

def fmt_srt(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60); ms = int(round((s % 1) * 1000))
    if ms >= 1000: ms = 999
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

ass_lines = [ass_header]
srt_lines = []

for idx, seg in enumerate(seg_list, 1):
    text = seg.text.strip()
    if not text: continue
    ass_lines.append(f"Dialogue: 0,{fmt_ass(seg.start)},{fmt_ass(seg.end)},Default,,0,0,0,,{text}")
    srt_lines.append(f"{idx}\\n{fmt_srt(seg.start)} --> {fmt_srt(seg.end)}\\n{text}\\n")

out_ass.write_text("\\n".join(ass_lines) + "\\n", encoding="utf-8")
out_srt.write_text("\\n".join(srt_lines) + "\\n", encoding="utf-8")
print(f"Generated subtitles: {out_ass.name}, {out_srt.name}")
"""
        worker_script.write_text(worker_code, encoding="utf-8")

    cmd = [
        *python_command(tool_dir),
        str(worker_script),
        str(audio_video_file.resolve()),
        str(out_ass.resolve()),
        str(out_srt.resolve()),
        model_repo,
        device,
    ]

    print(f"[subtitles-whisper] Running Whisper large-v3-turbo ({model_repo}) on {device}...")
    proc = runtime.run(cmd, cwd=tool_dir, env=tool_env(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Whisper transcription failed: {proc.stderr or proc.stdout}")

    return out_ass, out_srt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} video-subtitles",
        description="Generate .ass/.srt subtitles using Whisper large-v3-turbo downloaded from HuggingFace.",
    )
    parser.add_argument("--project-root", type=Path, required=True, help="Path to manga project directory.")
    parser.add_argument("--file", type=Path, default=None, help="Specific audio/video file. Defaults to latest joined video or merged audio.")
    parser.add_argument("--model-repo", default=MODEL_HF_REPO, help="HuggingFace model repo ID.")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    sub_dir = subtitles_root(project_root)
    sub_dir.mkdir(parents=True, exist_ok=True)

    input_file = args.file
    if input_file is None:
        # Search for joined video or audio
        output_mp4s = list((project_root / "output").glob("*_full*.mp4"))
        if output_mp4s:
            input_file = max(output_mp4s, key=lambda p: p.stat().st_mtime)
        else:
            audio_wavs = list((project_root / "audio").rglob("*.wav"))
            if audio_wavs:
                input_file = audio_wavs[0]

    if input_file is None or not input_file.is_file():
        print(f"[ERROR] No input media file found under {project_root}.", file=sys.stderr)
        return 1

    out_ass = sub_dir / f"{input_file.stem}.ass"
    out_srt = sub_dir / f"{input_file.stem}.srt"

    device = "cuda" if args.device in ("cuda", "auto") else "cpu"

    try:
        generate_subtitles_in_env(input_file, out_ass, out_srt, model_repo=args.model_repo, device=device)
    except Exception as exc:
        print(f"[ERROR] Subtitle generation failed: {exc}", file=sys.stderr)
        return 1

    result = {
        "ok": True,
        "project_root": str(project_root),
        "input": str(input_file),
        "ass": str(out_ass),
        "srt": str(out_srt),
    }
    emit_result(**result)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())