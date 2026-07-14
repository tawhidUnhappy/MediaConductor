# Production incidents & the invariants they created

Every entry here is a real failure that shipped (or nearly shipped) and the
rule that now prevents it. CLAUDE.md lists the rules as one-liners; this file
is the *why*, kept out of the hot context path. If you are about to "clean up"
one of these guards, read its story first — most of them look redundant right
up until they aren't.

## Audio / mixing

- **Music splice holes shipped in a public video (2026-07-06).** A raw
  `-stream_loop -1` of a rip with ~80 ms splice holes produced audible music
  cut-outs; the video had to be replaced. Now every BGM track is QC'd and
  repaired before mixing (`video_pipeline/music_bed.py`): a 20 ms RMS envelope
  scan finds sub-window holes `silencedetect` can't see, silent lead/tail is
  trimmed, and defective/short tracks are replaced by a crossfade-looped bed
  cached under `<work-dir>/music_bed/`. `--raw-music` bypasses; bed-prep
  failures fall back to the raw file.
- **`amix` default rescaling shipped ~−20 LUFS videos.** amix rescales every
  input by 1/inputs (−6 dB for two), and YouTube never boosts quiet uploads —
  they just played quiet. `amix=…:normalize=0` in `build_mix_filter()` is
  load-bearing; guarded by tests in `test_music_bed.py`.
- **`alimiter` default auto-normalization fought the whole gain chain.**
  `level=true` pushes output back toward 0 dBFS, undoing the −14 LUFS target.
  `alimiter=level=disabled` keeps it a pure peak catch; also test-guarded.
- **An unconditioned bed sounded "unmixed".** A raw track carries 6–10 LU of
  its own loudness range (the Thapin bed measured LRA 7.9), so it swelled and
  receded independently of the narration. `condition_bed()` bakes in an
  acompressor + a 2–5 kHz EQ dip; the conditioned (not raw) bed is what gets
  loudness-aligned, which is why `--music-volume-db` is a true LU separation.
- **High duck ratios degenerate into uniform quiet.** On wall-to-wall recap
  narration, sidechain ratio 4 measured as a constant 9 dB reduction instead
  of dips — keep the default ratio low (2).
- **A linear volume knob labelled "dB" confused users.** All volume controls
  are dB-native now; don't reintroduce a linear multiplier.
- **The −22 dB default offset** comes from dense-narration guidance (general
  voiceover −18…−20; continuous speech masks more). −15 masks the voice on
  phone speakers, −25 is inaudible. Keep new defaults inside −18…−24. (Was
  −19; a real listen found it a touch loud.)

## GPU / TTS

- **`torch.backends.cudnn.benchmark = True` crashes concurrent workers**
  (`CUDNN_STATUS_EXECUTION_FAILED` — re-benchmarking races across processes).
  Must stay `False` in `kokoro_batch_worker.py`.
- **8 GPU workers crashes an RTX 3060 even with benchmark off** (too many
  CUDA contexts); 4 is stable in production. Enforced since 2026-07 by
  `clamp_gpu_workers()` in `video_pipeline/common.py`
  (`MANGAEASY_UNSAFE_GPU_WORKERS=1` opts out on tested hardware).
- **Multi-worker resume pruned the wrong files.** `--resume-audio` deletes
  the last N written files, but the manifest is sharded before pruning runs —
  so pruning must be per-shard (`prune_recent_audio_for_resume(...,
  shards=...)`). If you change sharding, keep resume-pruning shard-aware.
- **Rising GPU/RAM over a long run is not a leak** — PyTorch's caching
  allocator never returns memory to the OS. Mitigated by periodic
  `gc.collect()` + `empty_cache()` every `CACHE_RELEASE_INTERVAL` items.

## Caches / installs

- **A global `HF_HOME`/`UV_CACHE_DIR` scattered multi-GB models outside the
  install.** `tool_env()` force-pins (not setdefault) all cache paths under
  `<data>/.mangaeasy/`; `MANGAEASY_SHARE_CACHES=1` opts back into sharing.
  Don't weaken the pin.
- **`tts_pipeline.py` used to force `HF_HOME` to `<cwd>/.hf_cache`,**
  overriding the tool_env pin from inside the subprocess — a second, competing
  cache. It is a `setdefault` fallback now (fixed 2026-07-14); config.py no
  longer mutates the environment at import either.
- **The frozen app's data root once resolved into `%TEMP%`** (Windows
  portable) and read-only mounts (macOS/Linux). Per-platform roots live in
  `_default_frozen_root()`; `MANGAEASY_ROOT` overrides. Never assume
  `~/.mangaeasy`.

## Pipeline correctness

- **An unconditional skip-if-exists silently joined six stale chapters** into
  a "successful" long video. Item renders are freshness-gated
  (`stale_reason()`); `--overwrite-video` forces. Don't restore the old skip.
- **Modules with private narration-loading copies didn't know about
  `intro.json`.** `load_narration()` in `video_pipeline/item_assets.py` is the
  only narration reader; never re-parse `narration.json` elsewhere.
- **The intro cold-open replayed a beat** ("why is the start repeating?" —
  viewer report): `intro.json` panels also appeared in `narration.json`.
  `narration-check` fails on the overlap now.
- **`--items 02` used to also select items 2.1/2.2** (first-integer parsing).
  Selection/sorting/join discovery compare `item_value()` (full numeric
  value), never `item_number()`.
- **Judging crops on downscaled contact sheets shipped sliced speech
  bubbles.** `webtoon-cutcheck` renders full-resolution review windows around
  every forced cut; that pass is mandatory before narration.
- **Merge indices computed by eye shipped wrong merges twice.**
  `webtoon-override` resolves indices from the ranges manifest — never
  hand-compute them.
- **Wrong speakers / multi-panel summaries / paraphrase drift** in shipped
  narration (viewer complaints): `panel-transcript` (OCR) now runs BEFORE
  narration is written, and `narration-review-sheets` pairs panel + narration
  + OCR for the semantic verification pass.

## Platform / integration

- **Piped stdout on Windows is cp1252 and crashed on "−14 LUFS".**
  `_force_utf8_stdio()` in `cli.py` forces UTF-8 — don't remove.
- **Upload-only YouTube tokens 403 on delete/update.** `store.SCOPES` now
  requests full video management; old tokens need a `youtube-auth` re-consent
  — it's not a code bug.
- **A dead OAuth token only surfaced mid-upload** (`invalid_grant`) after the
  whole video was built. Check `youtube-status --verify --json` before
  building/uploading.
- **YouTube force-locks unaudited API projects to private.** The CLI default
  stays `private`; if an upload arrives private despite `--privacy public`,
  the fix is YouTube's API audit, not re-uploading.
