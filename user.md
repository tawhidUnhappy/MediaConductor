# mangaEasy — Complete User Guide & Command Reference

Welcome to **mangaEasy**, an agent-native CLI and MCP toolkit for producing **manga, manhwa, and webtoon recap videos**. 

This guide explains how to install, configure, and use the complete application end-to-end, followed by an exhaustive reference of **every single CLI command** available.

---

## 1. Directory & Isolation Architecture

`mangaEasy` uses a strict **100% project-isolated directory structure**. Every generated file, audio clip, video, scratch render, and review record lives directly inside that specific manga's project folder under `data/library/<manga_name>/`.

```text
data/library/<manga_name>/
├── manga.json               (MangaDex source record)
├── MEMORY.json              (Project story memory)
├── .mangaeasy/              (Hash-bound review approvals)
├── 01/                      (Chapter folder: download/ pages, panels/, narration.json, transcript.json)
├── audio/                   (Raw per-panel TTS .wav files)
├── audio_faded/             (8ms edge-faded audio derivatives)
├── output/                  (Rendered item MP4s, joined long MP4, quality reports)
│   ├── items/               (item_01.mp4, item_02.mp4, etc.)
│   └── <manga_name>_full_TIMESTAMP.mp4
├── review/                  (Visual review sheets and evidence)
├── subtitles/               (Generated .ass and .srt subtitle files)
├── zips/                    (Packed reading sheet & context ZIPs <= 1 GB)
└── work/                    (Scratch files, detection overlays, job logs)
```

**Key Benefit:** To back up, move, or delete a manga project, you only need to manage `data/library/<manga_name>/`. Nothing leaks into global folders.

---

## 2. End-to-End Workflow Guide

### Step 1: Initial Setup & Verification
Run setup once from the root directory to provision core binaries (`ffmpeg`, `ffprobe`, `uv`, `git-lfs`) and AI tool environments:
```bash
uv sync
uv run mangaeasy setup --mode manga-video
uv run mangaeasy doctor --mode manga-video --json
uv run mangaeasy smoke-test
```

---

### Step 2: Download Manga Chapters
Download a chapter or series from MangaDex into `data/library/<manga_name>/`:
```bash
uv run mangaeasy download --url "https://mangadex.org/title/<MANGA_URL_OR_UUID>" --name "if_her_flag_breaks" --chapters "01-05"
```
*(Use `--all` instead of `--chapters` to download all available chapters).*

---

### Step 3: Format Detection & Panel Cropping

1. **Detect whether the manga is Webtoon (vertical strip) or Paged (standard comic grid):**
   ```bash
   uv run mangaeasy style-detect --project-root data/library/if_her_flag_breaks --items 01-05
   ```

2. **Crop into individual panels:**
   * **For Paged Manga:**
     ```bash
     uv run mangaeasy page-split --project-root data/library/if_her_flag_breaks --items 01-05
     ```
   * **For Webtoon Strips:**
     ```bash
     uv run mangaeasy webtoon-split --project-root data/library/if_her_flag_breaks --items 01-05
     ```

---

### Step 4: Generate Reading Sheets & Context ZIPs

1. **Render multi-panel reading sheets (3–8 panels per sheet):**
   ```bash
   uv run mangaeasy panel-reading-sheets --project-root data/library/if_her_flag_breaks --items 01-05
   ```

2. **Pack generated reading sheets into ZIP files (<= 1 GB each) for distribution or AI context:**
   ```bash
   uv run mangaeasy sheets-pack --project-root data/library/if_her_flag_breaks
   ```
   *(Files are saved in `data/library/if_her_flag_breaks/zips/`)*.

---

### Step 5: Narration Script & Semantic Review

1. **(Optional) Run DeepSeek-OCR 2 on panel speech bubbles:**
   ```bash
   uv run mangaeasy panel-transcript --project-root data/library/if_her_flag_breaks --items 01-05
   ```

2. **Create/Edit the Narration Script:**
   Edit `data/library/if_her_flag_breaks/01/narration.json` or use the CLI editor:
   ```bash
   uv run mangaeasy narration-edit --project-root data/library/if_her_flag_breaks --item 01 --set "ch01_001.jpg" "Our protagonist enters the ancient hall."
   ```

3. **Check Script Structure & Generate Review Sheets:**
   ```bash
   uv run mangaeasy narration-check --project-root data/library/if_her_flag_breaks --items 01-05
   uv run mangaeasy narration-review-sheets --project-root data/library/if_her_flag_breaks --items 01-05
   ```

4. **Record Approval Gate:**
   ```bash
   uv run mangaeasy manga-review crop --project-root data/library/if_her_flag_breaks --items 01-05 --reviewer "your_name"
   uv run mangaeasy manga-review narration --project-root data/library/if_her_flag_breaks --items 01-05 --reviewer "your_name"
   ```

---

### Step 6: Audio Synthesis & Subtitle Generation

1. **Generate Narration Audio (Kokoro TTS / IndexTTS):**
   ```bash
   uv run mangaeasy video-audio --project-root data/library/if_her_flag_breaks --items 01-05 --tts auto
   ```

2. **Generate `.ass` and `.srt` Subtitles using Whisper:**
   ```bash
   uv run mangaeasy video-subtitles --project-root data/library/if_her_flag_breaks
   ```

---

### Step 7: Video Rendering, Joining & Audio Mixing

1. **Render individual chapter videos and join into a long recap video:**
   ```bash
   uv run mangaeasy video --project-root data/library/if_her_flag_breaks --items 01-05 --build-long-video --normalize-audio
   ```

2. **(Optional) Add or Mix Background Music:**
   ```bash
   uv run mangaeasy video-add-bgm --project-root data/library/if_her_flag_breaks --background-music "bgm/theme.wav" --music-volume-db -28
   ```

3. **Generate YouTube Chapter Timestamps:**
   ```bash
   uv run mangaeasy video-chapters --project-root data/library/if_her_flag_breaks --items 01-05
   ```

---

### Step 8: Quality Gate & Publishing

1. **Run the Encoded Quality Gate:**
   ```bash
   uv run mangaeasy video-quality --project-root data/library/if_her_flag_breaks
   ```

2. **Compose a Thumbnail:**
   ```bash
   uv run mangaeasy thumbnail-candidates --project-root data/library/if_her_flag_breaks
   uv run mangaeasy thumbnail-compose --base data/library/if_her_flag_breaks/01/panels/ch01_001.jpg --output data/library/if_her_flag_breaks/thumb.png --preset label-arrow --text "VILLAIN" --check
   ```

3. **Record Final Video Approval:**
   ```bash
   uv run mangaeasy manga-review final-video --project-root data/library/if_her_flag_breaks --items 01-05 --video data/library/if_her_flag_breaks/output/if_her_flag_breaks_full.mp4 --reviewer "your_name"
   ```

4. **Upload to YouTube:**
   ```bash
   uv run mangaeasy youtube-upload --profile default --project-root data/library/if_her_flag_breaks --video data/library/if_her_flag_breaks/output/if_her_flag_breaks_full.mp4 --title "Reincarnated As A Villain - Manga Recap" --thumbnail data/library/if_her_flag_breaks/thumb.png
   ```

---

## 3. Complete CLI Command Reference (All 75 Commands)

Below is the exhaustive list of every command provided by `mangaEasy`, categorized by functionality.

### Group 1: Setup, System & Environment (16 Commands)

1. **`mangaeasy setup`**
   * **Description:** One-command provisioning of core binaries (`ffmpeg`/`ffprobe`, `uv`, `git-lfs`) and AI tool environments.
   * **Syntax:** `uv run mangaeasy setup [--mode manga-video] [--all] [--minimal] [--dry-run] [--skip TOOL]`

2. **`mangaeasy doctor`**
   * **Description:** Check system readiness, installed executables, GPU acceleration (`cuda`/`mps`/`cpu`), and tool status.
   * **Syntax:** `uv run mangaeasy doctor [--mode manga-video] [--json]`

3. **`mangaeasy commands`**
   * **Description:** Display the complete command catalog or output the JSON schema.
   * **Syntax:** `uv run mangaeasy commands [--json] [--full] [--tools TOOL1 TOOL2] [--mode manga-video]`

4. **`mangaeasy modes`**
   * **Description:** Display production modes, required AI dependencies, and skill paths.
   * **Syntax:** `uv run mangaeasy modes [--mode manga-video] [--json]`

5. **`mangaeasy where`**
   * **Description:** Report resolved application paths (`data_root`, `runtime_home`, `tools_home`, `workspace_root`).
   * **Syntax:** `uv run mangaeasy where [--json]`

6. **`mangaeasy workspace-layout`**
   * **Description:** Audit all persistent roots and confirm whether they reside safely inside `data/` or `runtime/`.
   * **Syntax:** `uv run mangaeasy workspace-layout [--json] [--strict]`

7. **`mangaeasy workspace-reset`**
   * **Description:** Delete all generated and downloaded data in `data/` to return to a clean slate.
   * **Syntax:** `uv run mangaeasy workspace-reset [--confirm] [--keep-library] [--only SUBDIR]`

8. **`mangaeasy library-list`**
   * **Description:** Scan and list all manga projects under `data/library/` along with item counts and readiness.
   * **Syntax:** `uv run mangaeasy library-list [--project-root PATH] [--json]`

9. **`mangaeasy series-plan`**
   * **Description:** Slice project items into fixed upload batches (e.g. 12 chapters per video) and identify the next batch.
   * **Syntax:** `uv run mangaeasy series-plan --project-root PATH [--batch-size 12] [--json]`

10. **`mangaeasy series-mark-published`**
    * **Description:** Record a completed upload batch in `publish.json`.
    * **Syntax:** `uv run mangaeasy series-mark-published --project-root PATH --items 01-12 --video-id VIDEO_ID`

11. **`mangaeasy mcp`**
    * **Description:** Launch the JSON-RPC stdio Model Context Protocol (MCP) server.
    * **Syntax:** `uv run mangaeasy mcp [--allow-root PATH] [--mode manga-video]`

12. **`mangaeasy smoke-test`**
    * **Description:** Run an end-to-end synthetic pipeline test to verify encoding and rendering functionality.
    * **Syntax:** `uv run mangaeasy smoke-test [--tts silent|kokoro] [--keep]`

13. **`mangaeasy install-tool`**
    * **Description:** Install or update an isolated AI tool environment (`kokoro-82m`, `index-tts`, `magi-v3`, `deepseek-ocr2`, `whisper-turbo`).
    * **Syntax:** `uv run mangaeasy install-tool <tool_name> [--skip-model]`

14. **`mangaeasy bootstrap-tools`**
    * **Description:** Download portable vendor binaries (`ffmpeg`, `ffprobe`, `uv`, `git-lfs`).
    * **Syntax:** `uv run mangaeasy bootstrap-tools [--system-ok]`

15. **`mangaeasy tool-downloads`**
    * **Description:** Show URLs and SHA-256 digests for all portable core tools across operating systems.
    * **Syntax:** `uv run mangaeasy tool-downloads [--json] [--all]`

16. **`mangaeasy env`**
    * **Description:** Print environment exports required to isolate caches inside the install directory.
    * **Syntax:** `uv run mangaeasy env [--sh|--bat|--ps1|--json] [--check]`

---

### Group 2: Background Job Management (3 Commands)

17. **`mangaeasy job-start`**
    * **Description:** Launch a long-running tool as a supervised, detached background process.
    * **Syntax:** `uv run mangaeasy job-start --tool TOOL_NAME --arguments-json '{"key":"value"}'`

18. **`mangaeasy job-status`**
    * **Description:** Inspect status, progress, exit code, and log output of a background job.
    * **Syntax:** `uv run mangaeasy job-status <job_id> [--tail 20] [--json]`

19. **`mangaeasy jobs`**
    * **Description:** List all active and historical background jobs.
    * **Syntax:** `uv run mangaeasy jobs [--json]`

---

### Group 3: Multi-Agent & Memory Coordination (7 Commands)

20. **`mangaeasy work-status`**
    * **Description:** Display stage dashboard, active leases, notes, and unclaimed next tasks.
    * **Syntax:** `uv run mangaeasy work-status --project-root PATH [--next] [--json]`

21. **`mangaeasy work-claim`**
    * **Description:** Acquire, renew, or release a TTL lease on an item stage or shared resource (e.g. `gpu`).
    * **Syntax:** `uv run mangaeasy work-claim --project-root PATH --item 01 --stage narrate [--ttl-minutes 60] [--release] [--renew]`

22. **`mangaeasy work-note`**
    * **Description:** Append or list notes in the shared project notebook (`notes.jsonl`).
    * **Syntax:** `uv run mangaeasy work-note --project-root PATH [--add "TEXT"] [--topic characters|speakers|tone] [--list]`

23. **`mangaeasy work-todo`**
    * **Description:** Manage plan-level tasks in the append-only event log (`todo.jsonl`).
    * **Syntax:** `uv run mangaeasy work-todo --project-root PATH [--add "TEXT"] [--start ID] [--done ID] [--reopen ID] [--remove ID] [--list]`

24. **`mangaeasy memory-init`**
    * **Description:** Initialize a fresh, isolated `MEMORY.json` story memory file for a manga project.
    * **Syntax:** `uv run mangaeasy memory-init --project-root PATH [--force]`

25. **`mangaeasy work-qa`**
    * **Description:** Run machine-checkable QA across crops, scripts, audio, and renders with fix commands.
    * **Syntax:** `uv run mangaeasy work-qa --project-root PATH [--items 01] [--errors-only] [--json]`

26. **`mangaeasy work-artifacts`**
    * **Description:** Inventory reusable generated artifacts.
    * **Syntax:** `uv run mangaeasy work-artifacts --project-root PATH [--json]`

---

### Group 4: Manga Acquisition, Cropping & OCR (9 Commands)

27. **`mangaeasy download`**
    * **Description:** Download chapters resumbly and politely from MangaDex.
    * **Syntax:** `uv run mangaeasy download --url "URL" [--name PROJECT] [--chapters "01-10"] [--all]`

28. **`mangaeasy style-detect`**
    * **Description:** Detect whether raw page images are vertical webtoons or paged manga.
    * **Syntax:** `uv run mangaeasy style-detect --project-root PATH [--items 01] [--json]`

29. **`mangaeasy gutter-split`**
    * **Description:** Low-level engine for detecting gutters and splitting image strips.
    * **Syntax:** `uv run mangaeasy gutter-split --input PATH --output PATH`

30. **`mangaeasy webtoon-split`**
    * **Description:** Crop vertical webtoon strips into panels with auto-split and gap rescue.
    * **Syntax:** `uv run mangaeasy webtoon-split --project-root PATH [--items 01] [--overrides FILE]`

31. **`mangaeasy webtoon-cutcheck`**
    * **Description:** Render full-resolution review windows around forced cuts and short panels.
    * **Syntax:** `uv run mangaeasy webtoon-cutcheck --project-root PATH [--items 01]`

32. **`mangaeasy webtoon-override`**
    * **Description:** Resolve merge/split coordinates and add corrections to an overrides file.
    * **Syntax:** `uv run mangaeasy webtoon-override --file FILE --project-root PATH --item 01 [--merge-at-cut Y] [--split-at Y]`

33. **`mangaeasy panels-remap`**
    * **Description:** Remap narration and audio files across panel re-numbering after a re-crop.
    * **Syntax:** `uv run mangaeasy panels-remap --project-root PATH [--items 01] [--apply]`

34. **`mangaeasy page-split`**
    * **Description:** Crop paged manga into panels using MAGI v3 AI detection.
    * **Syntax:** `uv run mangaeasy page-split --project-root PATH [--items 01] [--reading-direction auto|rtl|ltr]`

35. **`mangaeasy panel-transcript`**
    * **Description:** Run DeepSeek-OCR 2 to extract speech bubble text into `<item>/transcript.json`.
    * **Syntax:** `uv run mangaeasy panel-transcript --project-root PATH [--items 01] [--seed-only] [--force]`

---

### Group 5: Reading Sheets & Context Packaging (4 Commands)

36. **`mangaeasy panel-reading-sheets`**
    * **Description:** Render bounded multi-panel reading sheets (3–8 panels/sheet) for script writing.
    * **Syntax:** `uv run mangaeasy panel-reading-sheets --project-root PATH [--items 01] [--per-sheet 6]`

37. **`mangaeasy narration-review-sheets`**
    * **Description:** Render review sheets pairing panel images with narration text and OCR candidates.
    * **Syntax:** `uv run mangaeasy narration-review-sheets --project-root PATH [--items 01]`

38. **`mangaeasy sheets-pack`**
    * **Description:** Pack generated reading and review sheets into split ZIP files (<= 1 GB each) under `zips/`.
    * **Syntax:** `uv run mangaeasy sheets-pack --project-root PATH [--max-size-mb 1000]`

39. **`mangaeasy panels-context-pack`**
    * **Description:** Pack panel images with top filename banners into a ZIP file for AI context.
    * **Syntax:** `uv run mangaeasy panels-context-pack --panels-dir PATH --output ZIP_PATH`

---

### Group 6: Scripting, Audio & Subtitles (9 Commands)

40. **`mangaeasy narration-check`**
    * **Description:** Validate narration JSON structure, panel references, and full coverage.
    * **Syntax:** `uv run mangaeasy narration-check --project-root PATH [--items 01] [--json]`

41. **`mangaeasy narration-edit`**
    * **Description:** Upsert, delete, or list narration entries via CLI without manual JSON editing.
    * **Syntax:** `uv run mangaeasy narration-edit --project-root PATH --item 01 [--set IMAGE TEXT] [--delete IMAGE] [--prune-audio]`

42. **`mangaeasy video-audio`**
    * **Description:** Synthesize per-panel narration audio using Kokoro TTS or IndexTTS.
    * **Syntax:** `uv run mangaeasy video-audio --project-root PATH [--items 01] [--tts auto|kokoro|indextts] [--overwrite]`

43. **`mangaeasy video-audio-indextts`**
    * **Description:** Synthesize narration audio via IndexTTS 2 voice cloning.
    * **Syntax:** `uv run mangaeasy video-audio-indextts --project-root PATH --speaker-wav WAV_PATH`

44. **`mangaeasy video-subtitles`**
    * **Description:** Transcribe audio/video using Whisper large-v3-turbo to generate `.ass` and `.srt` subtitles.
    * **Syntax:** `uv run mangaeasy video-subtitles --project-root PATH [--device auto|cuda|cpu]`

45. **`mangaeasy video-audio-audit`**
    * **Description:** Audit per-panel WAV files for missing, zero-byte, or corrupt audio.
    * **Syntax:** `uv run mangaeasy video-audio-audit --project-root PATH [--fix]`

46. **`mangaeasy video-fade-audio`**
    * **Description:** Apply symmetric 8ms edge fades and adaptive declicking to narration WAVs.
    * **Syntax:** `uv run mangaeasy video-fade-audio --project-root PATH [--fade-ms 8.0]`

47. **`mangaeasy audio-takes-list`**
    * **Description:** List archived audio takes preserved during regenerations.
    * **Syntax:** `uv run mangaeasy audio-takes-list --project-root PATH [--json]`

48. **`mangaeasy audio-takes-restore`**
    * **Description:** Restore a previously archived audio take run back to active audio.
    * **Syntax:** `uv run mangaeasy audio-takes-restore --project-root PATH --run run_0001`

---

### Group 7: Video Rendering, Mixing & Quality Gates (12 Commands)

49. **`mangaeasy video`**
    * **Description:** Orchestrate the complete video pipeline (audio -> fades -> render -> join -> BGM -> normalize -> validate).
    * **Syntax:** `uv run mangaeasy video --project-root PATH [--items 01] [--build-long-video] [--normalize-audio]`

50. **`mangaeasy video-render`**
    * **Description:** Render individual 1080p MP4 videos for each chapter item from panels and audio.
    * **Syntax:** `uv run mangaeasy video-render --project-root PATH [--items 01] [--preset p5] [--fps 30]`

51. **`mangaeasy video-join`**
    * **Description:** Concatenate individual item MP4s into one full recap video.
    * **Syntax:** `uv run mangaeasy video-join --project-root PATH [--items 01-12] [--allow-gaps]`

52. **`mangaeasy video-add-bgm`**
    * **Description:** Mix background music into a long video with conditioning, EQ carving, and auto-ducking.
    * **Syntax:** `uv run mangaeasy video-add-bgm --project-root PATH --background-music BGM_PATH [--music-volume-db -28]`

53. **`mangaeasy video-normalize-audio`**
    * **Description:** Perform two-pass EBU R128 audio normalization (-14 LUFS / -1.5 dBTP).
    * **Syntax:** `uv run mangaeasy video-normalize-audio --input MP4_PATH [--replace]`

54. **`mangaeasy video-validate`**
    * **Description:** Structurally validate stream codecs, aspect ratios, durations, and audio/video alignment.
    * **Syntax:** `uv run mangaeasy video-validate --project-root PATH [--items 01]`

55. **`mangaeasy video-chapters`**
    * **Description:** Generate paste-ready YouTube chapter timestamps from rendered video stream durations.
    * **Syntax:** `uv run mangaeasy video-chapters --project-root PATH [--items 01-12]`

56. **`mangaeasy video-quality`**
    * **Description:** Measure encoded deliverable loudness, true peak, A/V drift, black frames, and extract review stills.
    * **Syntax:** `uv run mangaeasy video-quality --project-root PATH --video MP4_PATH`

57. **`mangaeasy video-clean-audio`**
    * **Description:** Archive or clear generated audio files for selected items.
    * **Syntax:** `uv run mangaeasy video-clean-audio --project-root PATH --items 01 --yes`

58. **`mangaeasy video-clean-video`**
    * **Description:** Delete rendered item MP4s and full long videos.
    * **Syntax:** `uv run mangaeasy video-clean-video --project-root PATH --yes`

59. **`mangaeasy video-clean-work`**
    * **Description:** Delete work scratch directories and temporary files.
    * **Syntax:** `uv run mangaeasy video-clean-work --project-root PATH --yes`

60. **`mangaeasy video-clean-all`**
    * **Description:** Delete all generated output for a project while preserving source chapters.
    * **Syntax:** `uv run mangaeasy video-clean-all --project-root PATH --dir TARGET_DIR --allowed-root ROOT --confirm-name NAME --yes`

---

### Group 8: Review & Publishing (13 Commands)

61. **`mangaeasy manga-review`**
    * **Description:** Record or verify hash-bound approvals for crops, narration scripts, or final MP4s.
    * **Syntax:** `uv run mangaeasy manga-review <crop|narration|final-video|check> --project-root PATH --reviewer NAME`

62. **`mangaeasy panel-decisions`**
    * **Description:** Audit or log historical panel omission decisions in `panel_decisions.json`.
    * **Syntax:** `uv run mangaeasy panel-decisions --project-root PATH --item 01 [--panels P1 P2] [--reason REASON]`

63. **`mangaeasy thumbnail-candidates`**
    * **Description:** Score cropped panels on detail and ratio to generate thumbnail candidate contact sheets.
    * **Syntax:** `uv run mangaeasy thumbnail-candidates --project-root PATH [--top 20]`

64. **`mangaeasy thumbnail-compose`**
    * **Description:** Composite a 1280x720 thumbnail with text, block arrows, speech bubbles, and chapter badges.
    * **Syntax:** `uv run mangaeasy thumbnail-compose --base PANEL_PATH --output OUT_PATH [--preset label-arrow|bubble|split] [--check]`

65. **`mangaeasy title-check`**
    * **Description:** Verify recap titles against house patterns, character limits, and formatting rules.
    * **Syntax:** `uv run mangaeasy title-check "TITLE_STRING" [--pattern]`

66. **`mangaeasy youtube-profiles`**
    * **Description:** List configured YouTube account profiles and cached channel details.
    * **Syntax:** `uv run mangaeasy youtube-profiles [--json]`

67. **`mangaeasy youtube-auth`**
    * **Description:** Authorize a YouTube account profile via browser OAuth.
    * **Syntax:** `uv run mangaeasy youtube-auth [--profile NAME] [--client-secrets FILE]`

68. **`mangaeasy youtube-status`**
    * **Description:** Check connection status or verify token validity with YouTube.
    * **Syntax:** `uv run mangaeasy youtube-status [--profile NAME] [--verify]`

69. **`mangaeasy youtube-logout`**
    * **Description:** Disconnect a YouTube account profile and revoke its tokens.
    * **Syntax:** `uv run mangaeasy youtube-logout [--profile NAME]`

70. **`mangaeasy youtube-upload`**
    * **Description:** Perform a resumable upload of a reviewed video to YouTube.
    * **Syntax:** `uv run mangaeasy youtube-upload --profile NAME --project-root PATH --video MP4_PATH --title TITLE`

71. **`mangaeasy youtube-list`**
    * **Description:** List uploaded videos, privacy statuses, and IDs for a connected channel profile.
    * **Syntax:** `uv run mangaeasy youtube-list [--profile NAME] [--limit 25]`

72. **`mangaeasy youtube-delete`**
    * **Description:** Delete a video from YouTube (requires two-step `--confirm`).
    * **Syntax:** `uv run mangaeasy youtube-delete --profile NAME --video-id VIDEO_ID [--confirm]`

73. **`mangaeasy youtube-thumbnail`**
    * **Description:** Update or replace the custom thumbnail on a live YouTube video.
    * **Syntax:** `uv run mangaeasy youtube-thumbnail --profile NAME --video-id VIDEO_ID --image IMAGE_PATH`

---

### Group 9: External AI Tools (2 Commands)

74. **`mangaeasy tools`**
    * **Description:** Display environment paths and resolution status for all external AI tools.
    * **Syntax:** `uv run mangaeasy tools [--json]`

75. **`mangaeasy index-tts`**
    * **Description:** Direct CLI access to run IndexTTS 2 synthesis inside its isolated environment.
    * **Syntax:** `uv run mangaeasy index-tts --project-root PATH --speaker-wav WAV_PATH`