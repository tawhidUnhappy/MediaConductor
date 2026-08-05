"""Keyword-based SFX trigger matching and FFmpeg audio filtergraph generation."""

from __future__ import annotations

from pathlib import Path

SFX_MAP = {
    "slash": "sfx/sword_slash.wav",
    "sword": "sfx/sword_slash.wav",
    "boom": "sfx/explosion.wav",
    "explode": "sfx/explosion.wav",
    "shock": "sfx/dramatic_gasp.wav",
    "gasp": "sfx/dramatic_gasp.wav",
    "punch": "sfx/heavy_hit.wav",
    "hit": "sfx/heavy_hit.wav",
}


def detect_sfx_triggers(entries: list[dict], sfx_dir: Path) -> list[tuple[float, Path]]:
    """Scan narration text for trigger keywords and return (timestamp_sec, sfx_path)."""
    triggers = []
    curr = 0.0
    for entry in entries:
        text = str(entry.get("narration", "")).lower()
        dur = float(entry.get("duration", 3.0))
        for kw, rel_path in SFX_MAP.items():
            sfx_file = sfx_dir / rel_path
            if kw in text and sfx_file.is_file():
                triggers.append((curr + 0.1, sfx_file))
                break
        curr += dur
    return triggers


def build_sfx_filtergraph(triggers: list[tuple[float, Path]]) -> tuple[list[str], str]:
    """Construct FFmpeg inputs and adelay/amix filtergraph for detected SFX."""
    if not triggers:
        return [], ""
    extra_inputs: list[str] = []
    filter_chain = ""
    mix_inputs = "[0:a]"
    for idx, (ts_sec, path) in enumerate(triggers, start=1):
        extra_inputs.extend(["-i", str(path)])
        delay_ms = int(ts_sec * 1000)
        filter_chain += f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume=0.4[sfx{idx}];"
        mix_inputs += f"[sfx{idx}]"
    filter_chain += f"{mix_inputs}amix=inputs={len(triggers)+1}:duration=first:normalize=0[aout]"
    return extra_inputs, filter_chain