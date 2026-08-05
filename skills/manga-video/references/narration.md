# Grounded manga narration

Read this reference after crop approval, before TTS. (`panel-transcript` OCR
is optional — see the workflow reference.)

## Source-of-truth gate

Narrate only after a vision-capable reviewer has cleared the crop pass. MAGI
boxes and DeepSeek OCR are machine proposals, never approvals or ground truth.
Use a staged crop review: inspect flagged/suspect overlays and crops first,
sample clean output, and broaden only when the sample shows systematic errors.
A complete source page or strip must not stand in for multiple panels. A cover,
title page, or genuinely borderless single-panel splash may remain page-sized
when visual review confirms it is one image beat; override it only when it
hides multiple bordered story panels. If you cannot inspect the images, stop
and hand the item to a vision-capable agent or human. Never create narration
from OCR alone.

## File contract

Create `<project-root>/<chapter>/narration.json` as a UTF-8 JSON array in
playback order. Each object requires an image basename that exists in the same
chapter's `panels/` folder and non-empty text to speak.

```json
[
  {
    "image": "ch01_001.png",
    "narration": "At the ruined gate, Mina realizes the guards have already fled."
  },
  {
    "image": "ch01_002.png",
    "narration": "Ren points toward the smoke and warns her that someone is still inside."
  }
]
```

The effective schema is:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["image", "narration"],
    "properties": {
      "image": {"type": "string", "minLength": 1},
      "narration": {"type": "string", "minLength": 1}
    },
    "additionalProperties": true
  }
}
```

`intro.json` is optional and uses the same shape. Its entries play before
`narration.json`; do not reference the same panel in both files. Do not replace
machine-generated `transcript.json` with narration.

## Authoring and review

Read the whole chapter in sequence once for context, then author each entry
with that exact original crop open at readable/full resolution. Panel pixels,
bubble tails, and the established reading sequence are authoritative.
`transcript.json`, when present, is an unverified second reading only. Resolve
any disagreement by re-reading the original panel; if it remains ambiguous,
use neutral wording or omit the uncertain claim and record a handoff note.

Describe only visible action and context established by the current or earlier
panels. Keep names, pronouns, relationships, abilities, locations, and speaker
attribution consistent across adjacent panels and chapters. Do not use future
knowledge, reveal a name early, invent dialogue, motives, causes, or off-panel
events, or turn an OCR guess into fact.

Write a high-engagement recap/explanation matching `/mnt/datadisk/narraction_example.txt`, not alt text or a bubble transcript. Open line 1 with an immediate narrative hook that drops directly into the scene. Use casual, dynamic storytelling phrasing ("our boy", "bro", "this guy", "the low-ranked kid", "dusted himself off", "played dumb", "insane feat", "messed up", "which brings us back to...", "and here's the creepy part because..."). Every crop in `panels/` must have one narration entry in playback order; omissions do not satisfy production coverage. Each line should carry one current story beat and, when supported, connect an already-established cause, decision, consequence, contrast, or stake. Keep pronouns unambiguous, orient the listener when time/place/speaker changes, and vary sentence openings and sentence shape. Avoid robotic inventories (`"Then he..."` on every panel), filler, meta wording such as `"the panel shows"`, and repeated paraphrases. If credits, scanlator notices, or decorative/SFX-only images remain in `panels/`, narrate them briefly and factually; otherwise fix the crop set before narration. Keep array order equal to the intended reading/playback order.

### Panel Synchronization & Anti-Desync Rules

- **Strict 1-to-1 Panel Alignment**: Entry `N` (`{"image": "panel_N.jpg", "narration": "..."}`) must describe ONLY the beat, dialogue, or action happening inside `panel_N.jpg`.
- **Zero Anti-Preview Desync**: Never describe panel `N+1`'s or `N+2`'s future action while showing panel `N`. Revealing upcoming events early causes audio to get ahead of the video screen.
- **Zero Retrospective Lag Desync**: Never spend panel `N`'s narration line describing past panel `N-1`'s action unless panel `N` visually displays a character's direct reaction to it.
- **Preserve Reading Filename Sequence**: `narration.json` array order must strictly match `panels/` reading order.
- **No Duplicate Intro Panels**: `intro.json` entries play before `narration.json`. Never use the same panel filename in both files — repeating a panel filename causes the video frame to play twice, resulting in a visual stutter desync.

**Voice delivery is always restrained.** Describe dramatic events and
characters' reactions accurately while the narrator remains a calm observer.
Express the feeling as natural prose rather than a performed laugh, scream, or
shout.

**Describe sound effects and reactions in prose; never perform them
phonetically.** IndexTTS/Kokoro pronounce real words and quiet interjections
fine ("hmm", "huh", ellipses like "even though...") but can garble or shout
"ghaha", "hahaha", "ha ha ha", "gyahahaha", or "aaaargh". Write what
happened instead: "he laughed", "she reacted in pain", or "the phoenix let
out a cry". Do not use exclamation marks, repeated punctuation, or shout-like
all-caps. `work-qa` treats these delivery violations as blocking errors, and
the audio/render preflight refuses to proceed if one remains.

Run both gates:

```bash
<mc> panel-reading-sheets --project-root D:/MediaProjects/library/example --items 01 --work-dir D:/MediaProjects/work
<mc> narration-check --project-root D:/MediaProjects/library/example --items 01 --json
<mc> narration-review-sheets --project-root D:/MediaProjects/library/example --items 01 --work-dir D:/MediaProjects/work
```

`panel-reading-sheets` is the cheap pre-narration reading pass: bounded 3-8
panel grids let the LLM follow sequence without spending tokens building its
own contact sheets. `narration-check` verifies structure, file references, and
strict all-panel coverage. It cannot establish semantic accuracy. Use review
sheets as an index: inspect OCR disagreements,
uncertain speakers, dense text, chronology changes, repetitive/robotic prose,
unclear pronouns, and awkward spoken phrasing first, then sample
straightforward entries. If the sample finds errors, broaden the pass. Compare
narration with the panel pixels, bubble tails, and sequence; the OCR column is
explicitly unverified and can be wrong. Correct mismatched panels, speaker
errors, unsupported claims, chronology drift, repetitive/robotic prose, unclear
pronouns, and awkward spoken phrasing, then rerun both gates. If TTS audio
already exists, use `narration-edit --prune-audio` or the documented
audio-audit repair flow so changed lines are regenerated.
