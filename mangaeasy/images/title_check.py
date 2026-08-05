"""mangaeasy.images.title_check — check a recap title against the house pattern.

``mangaeasy title-check`` reads a proposed YouTube title and reports the
mechanical faults: over YouTube's 100-character limit, missing the recap
suffix a returning viewer scans for, shouting in full capitals, emoji,
punctuation spam, a malformed chapter range.

The pattern it encodes is ``HOUSE_PATTERN`` below, taken from the titles this
channel already ships — ``title-check --pattern`` prints it in full.

Three things make those titles work, and none can be checked by a program:
the reversal has to be the actual turn of the story, the emphasis words have
to be the ones a browsing viewer recognises (``VILLAIN``, ``YANDERE``,
``ISEKAI'D``), and every claim has to be supported by a beat that appears in
the video. **A title that passes this check can still be a lie.** The check
covers the shape; whether the promise is true is the agent's judgement.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata

from mangaeasy.brand import CLI_NAME
from mangaeasy.utils import emit_result

# YouTube rejects anything longer. Search and mobile truncate far earlier
# (~70 characters), but the shipped house titles run to 97 and work, so the
# only length worth warning about is the one that actually breaks.
HARD_LIMIT = 100
COMFORTABLE_MAX = 98
THIN_BELOW = 40

RECAP_SUFFIXES = (
    " - manga recap", " - manhwa recap", " - manhua recap", " - webtoon recap",
    " | manga recap", " | manhwa recap", " | manhua recap", " | webtoon recap",
)

# "(1-6)", "(1-12)", "1-6" — the part marker on a multi-batch series.
RANGE_RE = re.compile(r"\(?\b(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\b\)?")
# A shouted word: 3+ letters, all caps. Apostrophes count as part of the word
# so ISEKAI'D reads as one emphasis, not two.
CAPS_WORD_RE = re.compile(r"\b[A-Z][A-Z'’]{2,}\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")

MAX_EMPHASIS_WORDS = 3

HOUSE_PATTERN = """\
The house recap-title pattern

    <STATUS or PREMISE> + <REVERSAL> [+ <CONSEQUENCE>] [(chapter range)] - <Manga|Manhwa> Recap

Shipped examples:

    He Refused To Become A Hero, So The Gods Cursed Him And He Became A Villain (1-6) - Manhwa Recap
    REINCARNATED As VILLAIN But The Heroines Are YANDERE for Him - Manga Recap
    Reincarnated As Villain He Ditches Main Story To Live In Peace! - Manga Recap
    REINCARNATED As The SECRET VILLAIN He Ditches Main Story To Live In Peace! - Manga Recap
    ISEKAI'D In a 1:5 Ratio World, He Turns Every Girl YANDERE - Manga Recap
    Isekai'd as Evil Villain but the Heroines Fall in Love with Him - Manga Recap
    When an Genius Reborn Into Valhalla Became The Valkyries Favorite!
    Farmer Accidentally Defeated The Demon Queen And She Fell In Love For His Strength | Manhwa Recap

How they are built

  1. Open on the status or premise the viewer can picture in three words:
     "Reincarnated As Villain", "Farmer", "ISEKAI'D In a 1:5 Ratio World".
  2. Turn it. The reversal is the whole title -- what the premise led you to
     expect, and what happened instead. No reversal, no click.
  3. Optionally land a consequence: "...And She Fell In Love For His Strength".
  4. Add the part marker "(1-6)" once a series runs past one batch.
  5. Close with " - Manga Recap" / " | Manhwa Recap" so returning viewers
     recognise the series in a crowded feed.

  Capitalise at most three words, and only ones a browsing viewer scans for
  (VILLAIN, YANDERE, ISEKAI'D, SECRET). Half the shipped titles use none --
  plain Title Case is fine. Title Case throughout, 65-97 characters, at most
  one '!' or '?', never both, no emoji.

Truthfulness is not optional and not checkable here: every claim must be
supported by a beat that actually appears in the video, and the title must
agree with the thumbnail. A title promising a betrayal the recap never
reaches is a misleading title even when every word is technically true."""


def _has_emoji(text: str) -> bool:
    return any(unicodedata.category(ch) == "So" or ord(ch) > 0x1F000 for ch in text)


def check_title(title: str) -> dict:
    """Report errors (block) and warnings (look again) for one title."""
    errors: list[str] = []
    warnings: list[str] = []
    raw = title
    stripped = title.strip()

    if not stripped:
        return {"ok": False, "title": raw, "errors": ["title is empty"], "warnings": [],
                "length": 0, "emphasis_words": [], "has_recap_suffix": False,
                "chapter_range": None}

    length = len(stripped)
    if length > HARD_LIMIT:
        errors.append(f"{length} characters — YouTube's limit is {HARD_LIMIT}; "
                      f"cut {length - HARD_LIMIT}")
    elif length > COMFORTABLE_MAX:
        warnings.append(f"{length} characters — search and mobile truncate near "
                        f"{COMFORTABLE_MAX}; the recap suffix may be cut off")
    if length < THIN_BELOW:
        warnings.append(f"only {length} characters — the house titles run 65-97 and "
                        f"carry a premise plus a reversal")

    if raw != stripped:
        warnings.append("leading or trailing whitespace")
    if "  " in stripped:
        warnings.append("double space")

    lowered = stripped.lower()
    has_suffix = any(lowered.endswith(suffix) for suffix in RECAP_SUFFIXES)
    if not has_suffix:
        warnings.append("no recap suffix — end with ' - Manga Recap' or ' | Manhwa Recap' "
                        "so a returning viewer recognises the series at a glance")

    words = WORD_RE.findall(stripped)
    emphasis = CAPS_WORD_RE.findall(stripped)
    if words and len(emphasis) >= max(3, len(words) - 2):
        errors.append("the whole title is in capitals — YouTube treats that as "
                      "shouting; emphasise 1-3 words instead")
    elif len(emphasis) > MAX_EMPHASIS_WORDS:
        warnings.append(f"{len(emphasis)} capitalised words ({', '.join(emphasis)}) — "
                        f"keep it to {MAX_EMPHASIS_WORDS} so the emphasis still lands")
    # Having no ALL-CAPS hook is deliberately NOT a warning: half the shipped
    # house titles are plain Title Case. Capitalising a word is an option for
    # the one term a browsing viewer scans for, not a requirement.

    if _has_emoji(stripped):
        errors.append("emoji — the house titles carry none, and they read as spam "
                      "in a recap feed")
    if stripped.count("!") > 1 or stripped.count("?") > 1:
        warnings.append("more than one '!' or '?' — one is the house maximum")
    if "!?" in stripped or "?!" in stripped or "!!" in stripped:
        warnings.append("stacked punctuation ('?!', '!!') reads as clickbait")

    match = RANGE_RE.search(stripped)
    chapter_range = None
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        chapter_range = match.group(0).strip("()")
        if high <= low:
            errors.append(f"chapter range '{chapter_range}' does not increase")

    return {
        "ok": not errors,
        "title": stripped,
        "length": length,
        "errors": errors,
        "warnings": warnings,
        "emphasis_words": emphasis,
        "has_recap_suffix": has_suffix,
        "chapter_range": chapter_range,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} title-check",
        description="Check a recap title against the house pattern: length, recap "
                    "suffix, emphasis words, punctuation, chapter range. Shape only — "
                    "whether the promise is true is your judgement.",
    )
    parser.add_argument("titles", nargs="*", metavar="TITLE",
                        help="One or more candidate titles (quote each one).")
    parser.add_argument("--pattern", action="store_true",
                        help="Print the house pattern and worked examples, then exit.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 when any title has warnings as well as errors.")
    args = parser.parse_args(argv)

    if args.pattern:
        print(HOUSE_PATTERN)
        return 0
    if not args.titles:
        parser.error("give at least one title, or --pattern")

    reports = [check_title(title) for title in args.titles]
    worst_ok = all(report["ok"] for report in reports)
    clean = all(report["ok"] and not report["warnings"] for report in reports)

    if args.as_json:
        print(json.dumps({"ok": worst_ok, "titles": reports}, ensure_ascii=False))
    else:
        for report in reports:
            mark = "ok  " if report["ok"] else "FAIL"
            print(f"[{mark}] {report['length']:>3} chars  {report['title']}")
            for error in report["errors"]:
                print(f"        error:   {error}")
            for warning in report["warnings"]:
                print(f"        warning: {warning}")
        print("\nShape only. Every claim in the title must be supported by a beat that "
              "actually appears in the video.")
    emit_result(ok=worst_ok, titles=reports)
    if not worst_ok:
        return 1
    return 1 if (args.strict and not clean) else 0


if __name__ == "__main__":
    raise SystemExit(main())
