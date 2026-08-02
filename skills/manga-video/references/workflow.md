# Manga Video workflow

The examples use the `<mc>` invocation selected by the parent skill and the
user-owned media workspace `D:/MediaProjects`. Run from the media workspace or
set `MANGAEASY_PROJECT_ROOT` to it for workspace-relative commands such as
`download`.

## Project layout

Pass the folder that directly contains chapter/item folders as
`--project-root`. The normal downloaded or imported layout is:

```text
D:/MediaProjects/library/example/     <- --project-root
  manga.json
  01/                                 <- chapter/item
    download/
      001.jpg                         <- source page image
      002.jpg
    panels/                           <- generated crops
    transcript.json                   <- generated panel OCR
    narration.json                    <- reviewed narration
  02/
    download/
      001.webp
```

For existing pages, copy or link them into
`<project>/<chapter>/download/<page image>`. If they must remain in another
folder such as `<chapter>/raw-pages/`, pass
`--source-subdir raw-pages` to `style-detect`, `webtoon-split`, `page-split`,
and `webtoon-cutcheck`. The default is `download`.

## Produce and verify

1. Orient and discover the exact current contract:

   ```bash
   <mc> where --json
   <mc> doctor --mode manga-video --json
   <mc> commands --mode manga-video --json --full
   <mc> library-list --project-root D:/MediaProjects --json
   ```

2. Acquire a title, or prepare the existing-image layout above:

   ```bash
   <mc> download --url "<MangaDex title URL>" --name example --all
   ```

3. Detect the format, inspect the returned sample images, then run exactly one
   crop path:

   ```bash
   <mc> style-detect --project-root D:/MediaProjects/library/example --items 01 --source-subdir download --json
   <mc> webtoon-split --project-root D:/MediaProjects/library/example --items 01 --source-subdir download --work-dir D:/MediaProjects/work
   # For paged manga, use page-split with the same roots and --source-subdir.
   ```

   Both splitters re-check the format per item and refuse a confident
   mismatch (webtoon pages into `page-split` or vice versa), naming the
   correct command; `--force-style` overrides only for deliberate
   mixed-format items.

4. Treat the splitter output as a proposal, not an approval. Open every source
   page overlay and every returned crop itself at readable/full resolution;
   contact sheets are an index and cannot prove that small text, faces, or
   borders survived. Apply `webtoon-override` or paged-manga box fixes and
   repeat the split until every crop is approved. Never infer approval from a
   command's exit code, MAGI confidence, a contact sheet, or file existence.

   If a split is repeated after `transcript.json` exists, immediately sync the
   affected transcript skeleton before reviewing or writing narration:

   ```bash
   <mc> panel-transcript --project-root D:/MediaProjects/library/example --items 01 --seed-only
   ```

   This keeps OCR only when a surviving panel filename still has the same
   SHA-256-bound crop bytes, drops rows for removed panels, and invalidates OCR
   whose crop bytes changed, without loading the model. A normal
   `panel-transcript` rerun fills those invalidated rows; alternatively, skip
   OCR and read the panel directly. Then re-run narration checks and review
   sheets; changed panel/narration inputs require regenerated audio and an
   overwritten render.

   A crop must fully contain its panel — never a partial edge, and never the
   whole source page/strip standing in for multiple panels or for a panel with
   its own border. A no-detection fallback, near-full-page MAGI box, or
   automatic near-full-source-strip range must be manually replaced. The only
   exception is a genuinely borderless single-panel splash; inspect it against
   the source and record an explicit manual accept before using it. Frame for
   the 16:9 landscape video frame the crop will be composited into: a squarish
   (1:1-ish) crop reads fine, but a box far taller than it is wide usually
   swallowed blank gutter above/below the art rather than hugging it, and
   shrinks to an unreadable sliver once fit to 16:9. `page-split` reports
   these as `tall_panel_boxes`; check each against its overlay and, when the
   excess really is gutter, tighten it with `--overrides` (leave it alone
   when the panel is genuinely that tall, e.g. a full-body action shot).

   Review every flagged location yourself against the source art. Record
   non-obvious accept/fix decisions so another agent does not repeat or undo
   the review:

   ```bash
   <mc> work-note --project-root D:/MediaProjects/library/example --topic crop-review --add "01 page 003: tall box is intentional full-body art; accepted"
   ```

5. Optionally OCR the panels before writing narration. The narrating agent
   reads bubble text from the panel images themselves; `panel-transcript` adds
   an independent, unverified DeepSeek reading that shows up as a cross-check
   column on the review sheets. Panel pixels, bubble tails, and established
   reading sequence remain authoritative. Run OCR when text is small/dense or
   a name spelling needs a second opinion; skip it freely otherwise (every
   later gate works without `transcript.json`; only a half-finished transcript
   is flagged as an interrupted run). OCR never substitutes for image access:
   if the narrator cannot see the images, stop and use the handoff in step 7.
   Because it is long-running, use the typed detached wrapper and poll the
   returned id:

   ```bash
   <mc> job-start --tool panel_transcript --arguments-json '{"project_root":"D:/MediaProjects/library/example","items":["01"],"device":"auto"}'
   <mc> job-status <job-id> --json
   ```

6. Maintain cast and speaker notes so attribution stays consistent across
   chapters. Read the shared notebook before narrating, and add only details
   attested by the panels or dialogue:

   ```bash
   <mc> work-note --project-root D:/MediaProjects/library/example --topic characters
   <mc> work-note --project-root D:/MediaProjects/library/example --topic characters --add "Ren = silver-haired swordsman; Mina names him in 01 panel 014"
   ```

   Use exactly the established names in narration. OCR may suggest a spelling,
   but confirm it against the panel before recording it as fact.

7. Read [narration.md](narration.md). Write one grounded
   `<chapter>/narration.json`, structurally check it, render semantic review
   sheets, and inspect every sheet:

   ```bash
   <mc> narration-check --project-root D:/MediaProjects/library/example --items 01 --json
   <mc> narration-review-sheets --project-root D:/MediaProjects/library/example --items 01 --work-dir D:/MediaProjects/work
   ```


7. Read [narration.md](narration.md). Write one grounded
   `<chapter>/narration.json`, structurally check it, render semantic review
   sheets, and inspect every sheet:

   ```bash
   <mc> narration-check --project-root D:/MediaProjects/library/example --items 01 --json
   <mc> narration-review-sheets --project-root D:/MediaProjects/library/example --items 01 --work-dir D:/MediaProjects/work
   ```

   Open every original crop at readable/full resolution while reviewing every
   line. Fix incorrect panel descriptions, dialogue meaning, speaker
   attribution, chronology, and spoken phrasing; treat OCR disagreements as a
   reason to re-read the pixels, not to overwrite them. Recap prose should
   connect already-established cause, choice, and consequence, keep pronouns
   clear, vary sentence openings, and avoid robotic panel-by-panel inventory.
   It must not invent motives, facts, dialogue, or future knowledge. Rerun both
   checks after every edit. Before proceeding to rendering, record crop and narration
   reviews using `manga-review crop` and `manga-review narration` with your agent identity.

8. Build using explicit roots. This complete foreground form is useful only
   when the harness can keep a long task alive:

   ```bash
   <mc> video --project-root D:/MediaProjects/library/example --audio-root D:/MediaProjects/audio --output-root D:/MediaProjects/output --work-dir D:/MediaProjects/work --items 01 --tts auto --build-long-video --normalize-audio --no-background-music
   ```

   Prefer the equivalent typed detached job in an ordinary agent session:

   ```bash
   <mc> job-start --tool run_full_pipeline --arguments-json '{"project_root":"D:/MediaProjects/library/example","audio_root":"D:/MediaProjects/audio","output_root":"D:/MediaProjects/output","items":["01"],"manual_review_confirmed":true,"tts":"auto","build_long_video":true,"normalize_audio":true,"no_background_music":true}'
   <mc> job-status <job-id> --json
   ```

   `job-start <cli-command> [args...]` remains accepted for existing scripts,
   but `--tool/--arguments-json` is the typed, schema-validated form published
   by `commands --json --full` and MCP. Ensure crop/narration review records are
   recorded before running. Keep background music below narration and re-render
   after any changed panel, narration, or audio input.

   Production defaults to separate `data/audio_faded/<project>/...` derivatives:
   every panel WAV gets a symmetric 8 ms fade-in and fade-out while the raw TTS
   under `data/audio/` remains untouched. Use `audio_source: raw` only for an
   intentional diagnostic comparison. With BGM, the order is join → mix music
   → one final two-pass whole-mix normalize to −14 LUFS / −1.5 dBTP. Any music
   change invalidates final normalization.

   The all-in-one command emits one parent-level progress marker per enabled
   stage, so poll `job-status` instead of inferring progress from file counts.
   It also runs the structural `video-validate` gate at the end by default;
   reserve `--no-validate` for an intentional diagnostic build.

9. Loop QA until clean, then validate the joined video:

   ```bash
   <mc> work-qa --project-root D:/MediaProjects/library/example --audio-root D:/MediaProjects/audio --output-root D:/MediaProjects/output --items 01 --json
   <mc> video-validate --project-root D:/MediaProjects/library/example --audio-root D:/MediaProjects/audio --output-root D:/MediaProjects/output --items 01 --json
   ```

   `video-validate` is a structural gate (coverage, streams, duration), not a
   complete media review. Before publishing, validate the
   final video, checking narration-to-panel pairing,
   crop readability, pacing, pronunciation, transition, and audio boundary.
   Record the final video review using `manga-review final-video`.

   Generate exact, ready-to-paste YouTube item timestamps from the rendered
   videos rather than adding durations manually:

   ```bash
   <mc> video-chapters --project-root D:/MediaProjects/library/example --output-root D:/MediaProjects/output --items 01-12
   ```

10. Create and visually inspect a thumbnail. Confirm source, music, voice, and
   corrected file using the same profile, replace the matching publish record
   (including profile/channel/replaced id when supported), then verify both the
   YouTube listing and `series-plan --json`.

Use absolute project/audio/output/work roots. Preserve `manga.json`,
`publish.json`, source pages, panels, and archived takes.
