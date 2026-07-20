# Video production improvements (2026-07-20)

This list records friction found while producing and checking a 24-item manga
recap, and turns the repeatable lessons into repository behavior or rules.

| Production friction | Improvement | Status |
|---|---|---|
| A selected `video-clean-audio` run removed panel WAVs but left the derived `_items/item_NN_narration.wav`, making stale audio look current. | Selected cleanup now archives or purges the matching combined item WAV, and targeted take restore restores it with the panel WAVs. | Implemented |
| A detached all-in-one build could spend hours in TTS/rendering while `job-status` had no useful parent-level progress. | `video` now emits an honest marker after every enabled stage: TTS, fades, render, join, BGM, normalize, and validation. | Implemented |
| `video-audio-audit` could ffprobe thousands of WAVs without showing movement. | Audits now report progress once per selected item; JSON mode sends ticks to stderr so stdout remains one clean JSON object. | Implemented |
| Re-cropping removed panels but old rows remained in `transcript.json` until someone noticed a count mismatch. | New rule: after every re-crop, run `panel-transcript --seed-only` for the affected items. It preserves OCR for surviving panels and drops stale rows without loading the OCR model. | Implemented as a production rule using existing behavior |
| YouTube item/chapter timestamps were calculated by probing every rendered MP4 and adding durations by hand. | `video-chapters` mirrors the joiner's item selection and sums video-stream durations (not AAC-extended container durations), then prints ready-to-paste timestamps or JSON. | Implemented |
| Structural validation was a separate command that an operator had to remember after a long build. | The all-in-one `video` command now runs `video-validate` as its final stage by default; `--no-validate` is reserved for deliberate diagnostics. | Implemented |
| Semantic narration, speaker attribution, crop framing, representative playback, and final loudness still require human/vision/audio judgment. | Keep the review-sheet and final media checks as mandatory gates; structural automation must not claim to replace them. | Rule retained intentionally |
| Reusing only text- and emotion-compatible WAVs from several archived takes required reconstructing historical narration state. | A content-addressed TTS cache could automate this, but it needs provenance metadata and collision-safe migration before it is trustworthy. | Deferred |
| There is no portable, graceful cancellation command for detached GPU jobs. | Add a supervisor-owned `job-stop` with process-tree termination and an explicit cancelled state. | Deferred |
| Rendering quality flags were easy to omit because speed/quality needs differ by machine and project. | Record and pass `--fps`, `--video-preset`, and encoder settings explicitly for a production build; do not silently change global defaults for every user. | Production rule |
| Final MP4s and thumbnails are multi-GB generated delivery artifacts that must not enter source control. | Keep them under the repository-relative `output_final/`; the root path is now ignored by Git. | Implemented |

The implemented changes are deliberately small and composable: they remove
stale state, expose progress, generate deterministic publishing metadata, and
make the existing structural gate part of the build. The deferred items need a
separate design because a partial implementation could lose expensive audio or
kill an unrelated process.
