# MediaConductor OCR — optional, untrusted panel text cross-evidence

DeepSeek-OCR 2 can propose text readings for manga panels. Its output may omit,
misread, or invent stylized text, so panel pixels, bubble tails, and established
reading order remain authoritative. OCR is optional and must never replace a
vision-capable reviewer opening the original panel.

## Files

- [`deepseek_ocr2_pipeline.py`](deepseek_ocr2_pipeline.py) — the pipeline that
  runs **inside the isolated `deepseek-ocr2` tool env** and adds an `ocr` field
  to each entry of the target narration JSON files. Driven by the
  `deepseek-ocr2` CLI command (dispatched via
  [`mediaconductor/tools/deepseek_ocr2.py`](../tools/deepseek_ocr2.py), which resolves
  the tool env and shells into it).
- [`panel_transcript.py`](panel_transcript.py) — creates optional
  `<item>/transcript.json` records and SHA-256-binds OCR to the exact panel
  bytes, invalidating stale OCR after a re-crop.

## Gotchas

- Needs the tool env: `mediaconductor install-tool deepseek-ocr2`. Like all external
  models it runs in its own `uv` env with pinned Torch/Transformers (see
  [`mediaconductor/tools/`](../tools/README.md)); this package only holds the
  in-env pipeline logic.
- `panel-transcript --force` replaces hash-matched `ocr` fields; changed panel
  bytes are invalidated and reprocessed without forcing.
- Item selection uses the same `--items 01 02` / `--item-range` tokens as the
  rest of the CLI.
