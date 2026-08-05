"""Generate ASS open captions from narration entries for video burn-in."""

from __future__ import annotations

import json
from pathlib import Path


def generate_ass_subtitles(entries: list[dict], output_ass: Path) -> Path:
    """Generate a styled ASS subtitle file from narration entries."""
    output_ass.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: RecapStyle,Impact,42,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,50,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    curr = 0.0
    for entry in entries:
        dur = float(entry.get("duration", 3.0))
        start_str = _fmt_time(curr)
        curr += dur
        end_str = _fmt_time(curr)
        text = str(entry.get("narration", "")).strip().replace("\n", " ")
        if text:
            events.append(f"Dialogue: 0,{start_str},{end_str},RecapStyle,,0,0,0,,{text}")
    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output_ass


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"