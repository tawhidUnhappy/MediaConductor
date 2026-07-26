"""Import-light narration delivery and fluency checks for TTS.

The "describe, don't perform" rule applies to narration text. Phonetic
laughs and vocal noises ("ghaha", "ha ha ha", "aaaargh") are not prose and
can make TTS shout or garble the line. State the event calmly instead ("he
laughed", "she reacted in pain"). Exclamation marks, repeated question marks,
and shout-like all-caps phrasing are also rejected by the delivery lint. Real
words and quiet interjections ("hmm", "huh", ellipses like "even though...")
remain valid; see ``narration_delivery_lint``.

A second rule keeps the narrator from sounding *broken* rather than loud.
Manga letters a stammer or a cut-off word to show emotion on the page
("Th- This is...?", "I... I guess...", "W... w... well..."). Spoken aloud that
is not emotion, it is a defect: the voice re-articulates each fragment and the
line sounds like a glitch. Narration states what the panel means instead
("he stares, startled", "she answers reluctantly"). Stammers, repeated words,
doubled ellipses, bare trailing dashes, and content-free fragments ("Huh...")
are rejected by ``narration_fluency_lint``.

This module is deliberately import-light (no torch, no indextts): the QA
loop, TTS/render preflight, and tests all use it outside the TTS environment.
"""

from __future__ import annotations

import re

# Narration text that spells out a laugh or another vocal sound instead of
# describing it in prose. The joined form includes the real-world failure that
# motivated this rule ("ghaha") as well as common variants. The spaced branch
# uses a back-reference so ordinary neighboring syllables do not match.
_JOINED_LAUGH = r"(?:(?:gya|kya|bwa|mwa|mua|mu|fu|ga|g)?(?:ha){2,}|(?:he|hi|ho|fu){2,})"
_SPACED_LAUGH = (
    r"(?:(?:g|gy|ky|bwa|mwa|mua|mu)?(?P<laugh>ha|he|hi|ho|fu))"
    r"(?:[\s,\-]+(?P=laugh)){1,}"
)
VOCAL_SFX_PATTERN = re.compile(
    rf"\b(?:{_JOINED_LAUGH}|{_SPACED_LAUGH}"
    r"|(?:gy|ky|gr|w)?(?P<scream_vowel>[aeiou])(?P=scream_vowel){2,}(?:h+|r+g+h*)?"
    r"|a+r+g+h+|u+g+h+|g+r{2,})\b",
    re.IGNORECASE,
)

# An exclamation mark directly asks most TTS engines for a more forceful
# delivery. Three or more all-caps words serve the same purpose. A single
# all-caps token is blocked only when it is a common shouted command, so real
# acronyms such as NASA, HTML, MMORPG, MC, and NPC remain valid.
_ALL_CAPS_RUN_PATTERN = re.compile(
    r"(?:\b[A-Z]{2,}\b(?:\s+|[,.]\s*)){2,}\b[A-Z]{2,}\b"
)
_ALL_CAPS_ACRONYMS = frozenset({
    "AI", "API", "DNA", "EU", "HQ", "HTML", "MC", "MMORPG", "MP",
    "NASA", "NATO", "NPC", "RPG", "UK", "UN", "US", "VR", "XP",
})
_SHOUT_CAPS_PATTERN = re.compile(
    r"\b(?:STOP|HELP|RUN|DIE|KILL|ATTACK|ESCAPE|WAIT|NEVER|NOW|LEAVE|SILENCE"
    r"|NO|GO|YES|FIRE|ENOUGH)\b"
)
_ELONGATED_VOWEL_PATTERN = re.compile(
    r"\b[A-Za-z]*(?P<vowel>[aeiou])(?P=vowel){2,}[A-Za-z]*\b",
    re.IGNORECASE,
)
_REPEATED_QUESTION_PATTERN = re.compile(r"\?{2,}")

# --- Fluency (listenability) --------------------------------------------
# Manga letters a stammer, a cut-off word, or a repeated syllable to show
# emotion on the page ("Th- This is...?", "I... I guess...", "W... w...
# well..."). Copied verbatim into narration these are actively unpleasant to
# listen to: TTS re-articulates the fragment as a separate word, so the
# narrator sounds broken rather than moved. Describe the feeling instead
# ("he stares, startled", "she answers reluctantly").
#
# A stutter is a *prefix* repeat ("Th- This"), which is what separates it from
# an ordinary hyphenated compound ("one-star", "B-rank", "mid-sentence") that
# reads perfectly well.
_STUTTER_PREFIX_PATTERN = re.compile(
    r"\b([A-Za-z]{1,3})[-–—]\s*(\1[A-Za-z]+)\b", re.IGNORECASE
)
# The same word repeated across an ellipsis or dash: "I... I", "the... the".
_STUTTER_REPEAT_PATTERN = re.compile(
    r"\b(\w+)\s*(?:\.{2,}|…|[-–—])\s*\1\b", re.IGNORECASE
)
# Adjacent duplicates are only a stutter for function words; "Bye Bye" and
# "had had" are ordinary English.
_STUTTER_FUNCTION_WORDS = (
    "a", "an", "the", "that", "this", "it", "i", "he", "she", "they", "we",
    "you", "is", "was", "to", "of", "and", "but", "in", "on", "my", "your",
)
_DUPLICATE_WORD_PATTERN = re.compile(
    r"\b(" + "|".join(_STUTTER_FUNCTION_WORDS) + r")\s+\1\b", re.IGNORECASE
)
# A line that ends on a bare dash has no closing word for TTS to land on.
_TRAILING_DASH_PATTERN = re.compile(r"[-–—]\s*[\"'”’]?\s*$")
_DOUBLE_ELLIPSIS_PATTERN = re.compile(r"(?:\.{2,}|…)\s*(?:\.{2,}|…)")
# "Huh...", "Is that...", "Um..." carry no information on their own and leave
# the listener with an unfinished thought. Four words or more is enough to
# carry a real beat, so only very short trail-offs are rejected.
_FRAGMENT_MAX_WORDS = 3

def narration_delivery_lint(text: str) -> str | None:
    """Return a calm-delivery problem with narration text, or ``None``.

    ``work-qa`` treats this as an error because unsafe text can create loud
    or garbled audio.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    match = VOCAL_SFX_PATTERN.search(text)
    if match:
        return (
            f"narration performs a laugh or vocal sound phonetically ({match.group(0)!r}); "
            "TTS can garble or shout it. Describe the event in calm prose instead, e.g. "
            "'he laughed' or 'she reacted in pain'."
        )
    if "!" in text:
        return (
            "narration contains an exclamation mark, which can trigger a loud or excited TTS delivery. "
            "Rewrite it as a calm statement ending with a period."
        )
    repeated_question = _REPEATED_QUESTION_PATTERN.search(text)
    if repeated_question:
        return (
            "narration contains repeated question marks, which can trigger an exaggerated TTS delivery. "
            "Rewrite it as a calm statement or use one question mark."
        )
    elongated = _ELONGATED_VOWEL_PATTERN.search(text)
    if elongated:
        return (
            f"narration elongates a word for vocal performance ({elongated.group(0)!r}). "
            "Rewrite it as normal calm prose."
        )
    caps = _SHOUT_CAPS_PATTERN.search(text)
    caps_run = _ALL_CAPS_RUN_PATTERN.search(text)
    if caps is None and caps_run is not None:
        words = set(re.findall(r"\b[A-Z]{2,}\b", caps_run.group(0)))
        if not words.issubset(_ALL_CAPS_ACRONYMS):
            caps = caps_run
    if caps:
        return (
            f"narration uses shout-like all-caps text ({caps.group(0)!r}). Rewrite it as normal-case, "
            "calm descriptive prose."
        )
    return None


def narration_fluency_lint(text: str) -> str | None:
    """Return a listenability problem with narration text, or ``None``.

    Complements :func:`narration_delivery_lint`: that rule keeps the narrator
    from becoming *loud*, this one keeps it from sounding *broken*. Both are
    errors in ``work-qa`` because both survive all the way into the rendered
    audio.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    stripped = text.strip()

    match = _STUTTER_PREFIX_PATTERN.search(stripped)
    if match:
        return (
            f"narration copies a stammer from the page ({match.group(0)!r}); TTS re-articulates the "
            "fragment as its own word. Describe the feeling instead, e.g. 'he stares, startled' or "
            "'she answers reluctantly'."
        )
    match = _STUTTER_REPEAT_PATTERN.search(stripped)
    if match:
        return (
            f"narration repeats a word for emotional effect ({match.group(0)!r}), which sounds like a "
            "glitch when spoken. State the emotion in prose instead, e.g. 'he hesitates before "
            "answering'."
        )
    match = _DUPLICATE_WORD_PATTERN.search(stripped)
    if match:
        return (
            f"narration doubles a word ({match.group(0)!r}). Remove the repeat or describe the "
            "hesitation in prose."
        )
    if _DOUBLE_ELLIPSIS_PATTERN.search(stripped):
        return (
            "narration contains two ellipses in a row, which renders as a long dead pause. "
            "Use one ellipsis, or rewrite the line as a complete sentence."
        )
    if _TRAILING_DASH_PATTERN.search(stripped):
        return (
            "narration ends on a bare dash with no closing word; TTS has nothing to land on. "
            "Finish the sentence, or use an ellipsis for a genuine trail-off."
        )
    if stripped.rstrip("?\"'”’").endswith(("...", "…")):
        words = [w for w in re.findall(r"[\w']+", stripped) if w]
        if len(words) <= _FRAGMENT_MAX_WORDS:
            return (
                f"narration is an unresolved fragment ({stripped!r}) that leaves the listener with no "
                "beat. Say what actually happens on the panel, e.g. 'he looks up, confused'."
            )
    return None
