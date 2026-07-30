# mangaeasy.audio — TTS generation internals

- `tts_pipeline.py` — the batch IndexTTS2 worker. **Runs inside the external
  `index-tts` tool env** (launched by `mangaeasy video-audio-indextts`, which
  sets `INDEX_TTS_ROOT` and the env's Python) — never import it from app
  code; it imports `indextts` at module scope and exits if that fails.
- `narration_safety.py` — import-light narration delivery and fluency checks.
  `narration_delivery_lint` blocks phonetic laughs/vocal noises ("ghaha", "ha
  ha ha", "aaaargh"), exclamation marks, and shout-like all-caps instead of
  allowing TTS to perform them loudly. `narration_fluency_lint` blocks
  stammers, repeated words, unresolved fragments, and broken punctuation that
  sound like synthesis glitches. `work-qa`, prompt docs, and tests use these
  checks outside the TTS environment; audio generation and rendering also run
  the central calm-narration preflight before doing expensive work.
