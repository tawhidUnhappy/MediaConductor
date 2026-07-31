# mangaeasy/images — publication packaging

Two helpers that turn approved panels into things you hand to a person or a
model. Generic image tooling (PDF export, format conversion, watermarking) used
to live here and was removed with the non-manga pipelines: none of it was on
the crop → narrate → video path, and each one was another surface the recap
guarantees had to be re-explained for.

## Files

| File | Command | Role |
|---|---|---|
| [`thumbnail_compose.py`](thumbnail_compose.py) | `thumbnail-compose` | text furniture onto a **source-panel** thumbnail base: stroked blocks, block-arrows, inset border ([docs/thumbnail.md](../../docs/thumbnail.md)) |
| [`ai_zip.py`](ai_zip.py) / [`ai_zip_cli.py`](ai_zip_cli.py) | `panels-context-pack` | pack a chapter's panels into a labelled ZIP so an LLM can read them as narration context (`panels_to_ai_zip`) |

## Entry points

Each command module exposes `main()` (its own `argparse`).
`ai_zip.panels_to_ai_zip(panels_dir, output, log, progress)` is the reusable
core behind `panels-context-pack`.

## Notes

- Thumbnail base art is an **approved source panel**, never generated art: the
  channel's value is the actual comic, and a generated cover promises art the
  video does not contain.
- The bundled `assets/fonts/edosz.ttf` brush face is available via `--font` for
  a manga-styled text block; the built-in candidates are Impact / Arial Bold /
  DejaVu Sans Bold.
- These read the chapter/panel layout via `mangaeasy.paths` helpers
  (`panels_dir`, `chapter_dir`, `download_dir`).
