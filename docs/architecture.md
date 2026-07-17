# Architecture

MediaConductor is intentionally split into a small `mangaeasy` compatibility
package and optional external AI tools, all driven through one primary CLI.

## One command

Everything is reachable through the `mediaconductor` entry point
(`mediaconductor.cli:main`; `mangaeasy` remains a 2.x alias). It is a thin
dispatcher: it maps a subcommand name to a
module and calls that module's `main()`, importing the module **lazily** so
`mediaconductor --help` never pulls in heavy optional dependencies.

```text
mediaconductor <command> [args...]  ->  mediaconductor.<area>.<module>:main()
```

## Main package

The main package contains:

- General item-based video pipeline in `mediaconductor.video_pipeline`
- Acquisition and cropping in `mediaconductor.download`, `mediaconductor.panels`,
  `mediaconductor.ocr`; image utilities in `mediaconductor.images`
- Command schemas shared by MCP and `commands --json --full` in
  `mediaconductor.command_spec`; detached background jobs in `mediaconductor.jobs`
- External tool lookup/wrappers in `mediaconductor.tools`
- Agent-facing prompts and in-tool-env scripts in `mediaconductor/assets/`

The default workspace root is the current working directory. Set
`MEDIACONDUCTOR_PROJECT_ROOT` to run commands against another folder.

## External tools

Kokoro, IndexTTS, MAGI, DeepSeek-OCR 2, and Z-Image Turbo can each keep their
own Python, CUDA, Torch, and Transformers dependencies as isolated `uv`
projects:

```text
<install folder>/.mangaeasy/tools/
  kokoro-82m/
  index-tts/
  magi-v3/
  deepseek-ocr2/
  z-image-turbo/
```

This avoids dependency conflicts while still allowing full GPU acceleration.

## GPU strategy

No GPU is required anywhere — every stage has a CPU path.

Tool installs (`mediaconductor install-tool`):

- Auto-detects hardware: CUDA torch builds only on Windows/Linux with an
  NVIDIA GPU; standard CPU builds everywhere else (macOS, AMD, plain CPU).
- Force a choice with `--cuda` or `--cpu`.

OCR:

- `mediaconductor deepseek-ocr2` runs inside the isolated DeepSeek-OCR 2 environment and
  writes an `ocr` field into narration JSON entries.
- `--device auto` uses CUDA when the tool env can see it, otherwise CPU.

Audio:

- `mediaconductor video --tts auto` (the default) picks IndexTTS when an NVIDIA GPU
  and the installed `index-tts` env are available, otherwise Kokoro.
- `mediaconductor video-audio` calls `kokoro-82m` with that tool's own Python.
- `--device auto` uses CUDA when available, otherwise CPU.
- `--device cuda` fails fast if CUDA is not visible.
- The IndexTTS bridge enables fp16/CUDA kernels only when CUDA is present.

Video:

- `--encoder auto` detects H.264 encoders exposed by FFmpeg.
- Preference order: `h264_nvenc`, `h264_amf`, `h264_qsv`,
  `h264_videotoolbox`, `libx264` (CPU, always available).

## Package data

`mediaconductor/assets/` ships only agent-facing prompts (`prompts/narration.md`)
and standalone scripts executed inside the external tool envs (`tools/`).
The old Flask templates/static files were removed with the GUI.
