# Thumbnail Guide

Thumbnails are composed from **approved source panels**, not from generated
art. That is the same rule the video follows: the channel's value is the actual
comic, and a generated cover promises art the video does not contain — which is
both a thumbnail-policy problem and a straightforward disappointment for the
viewer who clicks.

```bash
mediaconductor thumbnail-compose \
  --base data/library/<P>/01/panels/01_014_02.jpg \
  --output data/output/<P>/thumb.png \
  --text "HE WAS THE WEAKEST" --text "UNTIL THE GATE OPENED"
```

`--base` must be a panel the crop review already approved, and it has to be
listed in `rights.json` under `thumbnail_sources` — `manga-rights check` fails
closed without it.

## Composition

1280×720, built from base art + bold stroked text blocks (rotate/shadow
supported) + fat outlined block-arrows + a thin white inset border. Prefer
`--spec-json` for full control, inline, with no scratch file:

```bash
mediaconductor thumbnail-compose --base panel.jpg --output thumb.png --spec-json '{
  "blocks": [
    {"text": "HE WAS THE WEAKEST", "x": 40, "y": 60, "size": 96, "rotate": -4,
     "fill": "#FFE600", "shadow": true},
    {"text": "UNTIL THE GATE OPENED", "x": 40, "y": 190, "size": 72}
  ],
  "arrows": [{"from": [520, 300], "to": [760, 380], "width": 26}]
}'
```

Tilt the big hook block a few degrees and keep the arrows chunky, so the markup
reads hand-placed rather than templated. The bundled `edosz.ttf` brush face is
available as `--font` for a manga-styled block; the default candidates are
Impact/Arial Bold/DejaVu Sans Bold.

## Candidate selection is a human step

Compose several candidates from approved panels and choose deliberately:

- **One to three focal characters.** A crowd at 320×180 is a smudge.
- **One clear conflict or contrast** — the thing the title promises.
- **Two to four words maximum** if text is included, at a size that survives a
  phone-sized render. Check it at mobile scale, not at full size.
- **No face or text occlusion**: the duration badge sits bottom-right, so keep
  the payload out of that corner.
- **Title and thumbnail must agree.** A thumbnail implying a beat the video does
  not contain is a misleading thumbnail regardless of intent.
- **No sexual or gore emphasis**, and never a sexualized minor — most recap
  source material has teenage leads, so this is a live constraint, not a
  formality. `manga-rights check` requires those scans to be recorded clear.

Open every candidate at full size before uploading, especially faces, cropped
speech bubbles, and anything that could read as explicit or minor-coded.
`mediaconductor youtube-thumbnail` replaces a thumbnail on an existing video
without re-uploading, so an unsatisfying choice is cheap to fix — a published
misleading one is not.

## Titles

Generate several truthful candidates from the approved story beats, then pick:

- protagonist status → reversal or unusual power → stakes → **one** curiosity gap
- no keyword soup, no misleading capitalization
- every claim in the title must be supported by beats that appear in the video

For the full production workflow, see
[recap-video-playbook.md](recap-video-playbook.md#phase-9--thumbnail-1280720),
and [manga-quality-design.md](manga-quality-design.md) for where this sits in
the review model.
