"""Per-project reading-direction resolution.

The pipeline handles Japanese manga, Chinese manhua, Korean manhwa, and
webtoons — paged or strip format, right-to-left or left-to-right. Strip
format needs no page direction (top-to-bottom); for paged sources the panel
reading order is direction-dependent, and guessing wrong scrambles every
page's narrative order.

The source of truth is the manga itself: `mangaeasy download` records the
MangaDex ``originalLanguage`` into ``manga.json``, and
``project_reading_direction`` maps it — printed Japanese manga and
traditional Hong Kong manhua read right-to-left; Korean manhwa, mainland
digital manhua, and western comics read left-to-right. An install-wide
config default was the only fallback before, which silently applied one
direction to every project on the machine.

Resolution order (first hit wins), each step reported in the reason string:

1. explicit ``--reading-direction rtl|ltr`` on the command (handled by the
   caller — this module is only consulted for ``auto``);
2. ``manga.json`` → ``original_language``;
3. ``config.system.json`` → ``cut_page.reading_direction``;
4. ``rtl`` (the historical default).
"""

from __future__ import annotations

import json
from pathlib import Path

# MangaDex originalLanguage codes that read right-to-left in paged format.
# ja = Japanese manga; zh-hk = traditional Hong Kong print manhua. Mainland
# digital manhua ("zh") and Korean manhwa ("ko") read left-to-right.
RTL_LANGUAGES = frozenset({"ja", "zh-hk"})


def direction_for_language(language: str | None) -> str | None:
    """"rtl"/"ltr" for a MangaDex language code, or None when unknown."""
    if not language or not isinstance(language, str):
        return None
    code = language.strip().lower()
    if not code:
        return None
    return "rtl" if code in RTL_LANGUAGES else "ltr"


def project_reading_direction(project_root: Path) -> tuple[str, str]:
    """(direction, reason) for a project — never raises.

    The reason string is meant to be printed by the caller so agents can see
    *why* a direction was chosen and correct the record (or pass the flag)
    when the source metadata is wrong.
    """
    manga_json = Path(project_root) / "manga.json"
    try:
        record = json.loads(manga_json.read_text(encoding="utf-8-sig"))
        language = record.get("original_language")
        direction = direction_for_language(language)
        if direction:
            return direction, f"manga.json original_language={language}"
    except Exception:  # noqa: BLE001 — missing/corrupt manga.json falls through
        pass

    try:
        from mangaeasy.config import load_system_config

        configured = load_system_config().get("cut_page", {}).get("reading_direction")
        if configured in ("rtl", "ltr"):
            return configured, "config.system.json cut_page.reading_direction"
    except Exception:  # noqa: BLE001 — unreadable config falls through
        pass

    return "rtl", "default (no original_language recorded — set it in manga.json or pass --reading-direction)"
