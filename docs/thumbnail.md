# Thumbnails and titles

Thumbnails are built from **manga panels the crop review already approved**.
There is no image generation in this pipeline and there is not meant to be:
the channel's value is the actual comic, and generated key art promises art
the video does not contain — a thumbnail-policy problem and a plain
disappointment for whoever clicked.

The whole job is three steps: **find the panel, compose the markup, write the
title.** The first and third are judgement, and no command does them for you.

```bash
# 1. shortlist panels worth opening, with contact sheets
mangaeasy thumbnail-candidates --project-root data/library/<P> --item-range 01-12 --json

# 2. compose from the one you chose
mangaeasy thumbnail-compose --base data/library/<P>/03/panels/03_014_02.jpg \
    --output data/output/<P>/thumb.png --preset label-arrow --text "VILLAIN" \
    --badge "1-12" --check

# 3. check the title candidates
mangaeasy title-check "REINCARNATED As VILLAIN But He Just Wants Peace - Manga Recap"
```

## 1. Finding the panel

`thumbnail-candidates` scores every cropped panel in the batch on detail
(luminance spread — an empty sky is a smudge at 320×180), ink coverage,
shape against 16:9, and resolution; then writes numbered contact sheets to
`data/review/<project>/thumbnail-candidates/`.

**The score does not pick the thumbnail.** No pixel statistic knows which
panel shows the reversal the title promises, whose face is in it, or whether
a composition reads as a sexualized minor. It exists so you open twenty
full-resolution candidates instead of two thousand. Treat the ranking exactly
like MAGI's panel boxes: a proposal, never an approval.

What you are looking for, in order:

- **One to three focal characters.** A crowd at 320×180 is mush.
- **One clear conflict or contrast** — the thing the title promises.
- **A readable face**, ideally with a strong expression. The references that
  work are almost all faces.
- **Room for the markup.** A panel with a busy top-left has nowhere for the
  label to go.

The panel you pick must be listed in `rights.json` under `thumbnail_sources`;
`manga-rights check` fails closed without it.

## 2. Composing

`thumbnail-compose` renders a 1280×720 canvas from one panel (cover-cropped)
or several (split layout), then draws four kinds of markup. Three presets
reproduce the layouts the reference set actually uses — start from one and
adjust, because where the arrow points depends entirely on the panel.

### `--preset label-arrow` — the workhorse

A short ALL-CAPS label in yellow `#FFE600` with a thick black stroke, and a
fat block arrow running from it to the character it names. This is the most
repeated element in the reference set, and it works because it answers
"which one?" before the viewer has to parse the picture.

```bash
mangaeasy thumbnail-compose --base panel.jpg --output thumb.png \
  --preset label-arrow --text "VILLAIN" --badge "1-12" --check
```

Two labels on one thumbnail (`VILLAIN` left, `HEROINE` right, each with its
own arrow) is a proven variant — write them as an explicit spec:

```json
{
  "blocks": [
    {"text": "VILLAIN", "x": 40,  "y": 34, "size": 100, "rotate": -3, "fill": "#FFE600"},
    {"text": "HEROINE", "x": 900, "y": 60, "size": 100, "rotate": -2, "fill": "#FFE600"}
  ],
  "arrows": [
    {"from": [170, 150], "to": [300, 250], "width": 30},
    {"from": [1010, 175], "to": [930, 265], "width": 30}
  ]
}
```

### `--preset bubble` — when the hook is something said

A speech bubble carrying one real line of dialogue: `dark` (black bubble,
white brush lettering) for a possessive or menacing line, `light` (white
bubble, black text) for a plain statement. The bundled `edosz.ttf` brush face
is the default and is what makes it read as manga lettering rather than a
caption pasted on top.

```bash
mangaeasy thumbnail-compose --base panel.jpg --output thumb.png \
  --preset bubble --text "YOU'RE MINE" --check
```

Use a bubble when a character *said* the hook; use a label when the hook is a
description the narrator applies. Mixing both on one thumbnail crowds it.

### `--preset split` — before/after

Two panels side by side with a divider bar and a label under each
(`WEAK` | `STRONG`), with the chapter badge top-center. Good for a power
reversal, useless for anything subtler — the comparison has to be legible as
two states in a single glance.

```bash
mangaeasy thumbnail-compose --base weak.jpg --base strong.jpg \
  --output thumb.png --preset split --text "WEAK" --text "STRONG" \
  --badge "1-3" --badge-corner top-center --check
```

### The spec document

```json
{
  "layout":  {"kind": "split", "sources": ["a.jpg", "b.jpg"], "divider": 10},
  "blocks":  [{"text": "VILLAIN", "x": 40, "y": 34, "size": 104, "rotate": -3,
               "fill": "#FFE600", "stroke": "#000000", "shadow": true, "font": null}],
  "arrows":  [{"from": [170, 150], "to": [300, 250], "width": 30,
               "color": "#FFE600", "style": "block", "shadow": true}],
  "bubbles": [{"text": "YOU'RE MINE", "center": [270, 260], "rx": 168, "ry": 196,
               "style": "dark", "tail": [410, 450], "size": 56, "rotate": 0}],
  "badge":   {"text": "1-12", "corner": "top-left", "fill": "#FFE600", "size": 92},
  "border": true
}
```

Pass it inline with `--spec-json '{...}'`, or in a file with `--spec`.
Anything you set explicitly wins over the preset.

House treatment, learned from the reference set:

- **Yellow `#FFE600` with a black stroke ≈ 12 % of the font size.** Nothing
  else survives every background a manga panel can throw at it.
- **Tilt the hook block −2 to −5°.** Perfectly horizontal reads templated.
- **Keep arrows chunky** (`width` 26–34). A thin arrow disappears at phone size.
- **Two to four words maximum.** The title carries the sentence; the
  thumbnail carries the hook.
- **Keep the bottom-right corner clear** — YouTube stamps the duration there.

### `--check` and what it cannot see

`--check` reports mechanical faults and exits 3: text spilling off-canvas,
type below ~44 px (unreadable at the 320×180 most viewers see), elements
overlapping each other, and anything colliding with the duration badge.

It is deliberately narrow. It does not know whether the crop cuts a face in
half, whether the thumbnail matches the title, or whether the composition
reads as explicit or as a sexualized minor — most recap source material has
teenage leads, so that last one is a live constraint, not a formality. **Open
the PNG at full size and look at it.** A clean `--check` is not a review.

`mangaeasy youtube-thumbnail` replaces a thumbnail on an already-published
video without re-uploading, so a weak choice is cheap to fix; a published
misleading one is not.

## 3. Titles

`mangaeasy title-check --pattern` prints the house pattern in full. The
short version:

```
<STATUS or PREMISE> + <REVERSAL> [+ <CONSEQUENCE>] [(chapter range)] - <Manga|Manhwa> Recap
```

```
Reincarnated As Villain He Ditches Main Story To Live In Peace! - Manga Recap
REINCARNATED As VILLAIN But The Heroines Are YANDERE for Him - Manga Recap
He Refused To Become A Hero, So The Gods Cursed Him And He Became A Villain (1-6) - Manhwa Recap
Farmer Accidentally Defeated The Demon Queen And She Fell In Love For His Strength | Manhwa Recap
```

1. Open on a premise the viewer can picture in three words.
2. **Turn it.** The reversal is the whole title — what the premise led you to
   expect, and what happened instead. No reversal, no click.
3. Optionally land the consequence.
4. Add `(1-6)` once the series runs past one batch.
5. Close with ` - Manga Recap` / ` | Manhwa Recap` so returning viewers
   recognise the series.

Title Case throughout, 65–97 characters, at most three ALL-CAPS emphasis
words — and none is fine, half the shipped titles use none. One `!` or `?` at
most, never stacked, no emoji.

Generate several candidates from the approved story beats and check them
together:

```bash
mangaeasy title-check "candidate one" "candidate two" "candidate three" --json
```

`title-check` validates shape only. **A title that passes can still be a
lie.** Every claim must be supported by a beat that actually appears in the
video, and the title and thumbnail must agree with each other — a thumbnail
implying a beat the recap never reaches is misleading regardless of intent.

For where this sits in the production flow see
[recap-video-playbook.md](recap-video-playbook.md#phase-9--thumbnail-1280720),
and [manga-quality-design.md](manga-quality-design.md) for the review model.
