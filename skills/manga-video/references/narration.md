# Grounded manga narration

Read this reference after crop approval, before TTS. (`panel-transcript` OCR
is optional — see the workflow reference.)

## Source-of-truth gate

Narrate only after a vision-capable reviewer has opened every source page/strip
overlay and every crop at readable/full resolution. MAGI boxes and DeepSeek
OCR are machine proposals, never approvals or ground truth. A complete source
page or strip must not stand in for multiple panels; only a genuinely
borderless single-panel splash may remain page-sized, after an explicit manual
review decision. If you cannot inspect the images, stop and hand the item to a
vision-capable agent or human. Never create narration from OCR alone.

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

Write a recap/explanation, not alt text or a bubble transcript. Each line
should carry one current story beat and, when supported, connect an
already-established cause, decision, consequence, contrast, or stake. Keep
pronouns unambiguous, orient the listener when time/place/speaker changes, and
vary sentence openings and sentence shape. Avoid robotic inventories
(`"Then he..."` on every panel), filler, meta wording such as `"the panel
shows"`, and repeated paraphrases. Avoid narrating credits, scanlator notices,
and purely decorative/SFX panels unless they carry story information. Keep
array order equal to the intended reading/playback order.

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
<mc> narration-check --project-root D:/MediaProjects/library/example --items 01 --json
<mc> narration-review-sheets --project-root D:/MediaProjects/library/example --items 01 --work-dir D:/MediaProjects/work --output-root D:/MediaProjects/review/narration
```

`narration-check` verifies structure and file references. It cannot establish
semantic accuracy. Open every review sheet and every corresponding original
crop at readable/full resolution. Compare narration with the panel pixels,
bubble tails, and sequence; the OCR column is explicitly unverified and can be
wrong. Correct mismatched panels, speaker errors, unsupported claims,
chronology drift, repetitive/robotic prose, unclear pronouns, and awkward
spoken phrasing, then rerun both gates. Every line needs this source comparison,
not just entries where OCR looks suspicious. If TTS audio already exists, use
`narration-edit --prune-audio` or the documented audio-audit repair flow so
changed lines are regenerated.
