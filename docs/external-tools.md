# External Tools

Heavy model tools run in their own isolated `uv` environments, each with its
own `.venv`, Python, and CUDA/Torch stack. The easiest way to provision them is
`mediaconductor install-tool <name>` — see [install-tools.md](install-tools.md).

`READY.json` records a completed local installation, and `doctor` rechecks the
interpreter, adapters, model directories, and required model payloads without
contacting the network. IndexTTS and DeepSeek-OCR 2 use explicit model
revisions. Kokoro, MAGI, and the optional generic
Faster Whisper integration resolve model weights on first use and are therefore
not bit-reproducible yet.

## Lookup

Run:

```bash
mediaconductor tools
```

The resolver checks, in order:

1. The tool's environment variable:
   - `KOKORO_ROOT`
   - `INDEX_TTS_ROOT` (or legacy `INDEX_TTS_DIR`)
   - `MAGI_V3_ROOT` (or legacy `MAGI_V3_DIR`)
   - `DEEPSEEK_OCR2_ROOT` (or `DEEPSEEK_OCR2_DIR`)
   - `Z_IMAGE_TURBO_ROOT` (or `Z_IMAGE_TURBO_DIR`)
2. The managed tools dir: `<install folder>/.mangaeasy/tools/<name>`
   (override with `MEDIACONDUCTOR_TOOLS_DIR`)
If a tool has `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Unix),
MediaConductor uses it directly. Otherwise it falls back to `uv run --project`.

## TTS engine selection

`mediaconductor video` picks the engine automatically (`--tts auto`, the default):

- **IndexTTS** when an NVIDIA GPU is present, the `index-tts` env is installed
  with checkpoints, and the speaker reference WAV exists — best quality.
- **Kokoro** otherwise — light and fast enough on any CPU.

Force a specific engine with `--tts indextts` or `--tts kokoro`.

## Kokoro

Used by:

```bash
mediaconductor video          # default engine on machines without an NVIDIA GPU
mediaconductor video-audio
```

Install with `mediaconductor install-tool kokoro-82m`. MediaConductor sends a manifest
to `mediaconductor.video_pipeline.kokoro_batch_worker` and executes it inside the
Kokoro environment. Its model is a legacy first-use download from the current
Hub default revision, not an immutable installer snapshot.

## IndexTTS

Used by:

```bash
mediaconductor video          # default engine on NVIDIA GPU machines
mediaconductor video-audio-indextts
mediaconductor index-tts
```

Install with `mediaconductor install-tool index-tts`. IndexTTS stays isolated
because its dependency stack is large and can conflict with other tools. Its
source checkout and Hugging Face checkpoint are both immutable revisions, and
readiness verifies every required checkpoint payload.

## MAGI v3 (panel detection)

Used by panel detection when `MEDIACONDUCTOR_EXTERNAL_MAGI` is not `0`.

The external MAGI environment must expose:

```text
magi-v3/detect_magi.py
```

`mediaconductor install-tool magi-v3` creates this automatically — the adapter ships
inside the mediaconductor package (`mediaconductor/assets/tools/detect_magi.py`) and is
copied into the tool folder. The `ragavsachdeva/magiv3` model code/weights
download from the current Hugging Face default revision on the first run.

Set `MEDIACONDUCTOR_EXTERNAL_MAGI=0` only when the main package env has the `ml`
extra installed and you intentionally want in-process detection.

## DeepSeek-OCR 2

Used by:

```bash
mediaconductor deepseek-ocr2 --project-root content
mediaconductor deepseek-ocr2 --project-root content --item-range 01-24 --device cuda
```

Install with `mediaconductor install-tool deepseek-ocr2`. The installer creates an
isolated uv environment and downloads the `deepseek-ai/DeepSeek-OCR-2` model
from Hugging Face into `deepseek-ocr2/model`. The command scans narration JSON
files, finds each panel image, and adds an `ocr` field to every entry that does
not already have one. Both the optional source clone and model snapshot are
commit-pinned and locally health-checked. Use `--force` to regenerate existing
OCR, or pass
`--prompt "<image>\n<|grounding|>Convert the document to markdown."` for
document-style markdown OCR.

