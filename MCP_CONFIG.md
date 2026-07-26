# MediaConductor MCP configuration

Use one mode-scoped MediaConductor server at a time. The examples below run
the source checkout at `D:/MediaConductor` and allow it to access media only
under `D:/MediaProjects`.

Before registering the server, prepare the checkout once:

```powershell
uv sync --project D:/MediaConductor
```

## Complete `mcpServers` block

Copy this into a JSON-based MCP client configuration:

```json
{
  "mcpServers": {
    "media-conductor": {
      "command": "uv",
      "args": [
        "--project",
        "D:/MediaConductor",
        "run",
        "mediaconductor",
        "mcp",
        "--mode",
        "manga-video",
        "--allow-root",
        "D:/MediaProjects"
      ]
    }
  }
}
```

If the configuration file already has an `mcpServers` object, copy only this
entry inside it:

```json
"media-conductor": {
  "command": "uv",
  "args": [
    "--project",
    "D:/MediaConductor",
    "run",
    "mediaconductor",
    "mcp",
    "--mode",
    "manga-video",
    "--allow-root",
    "D:/MediaProjects"
  ]
}
```

Change `D:/MediaProjects` to the directory that contains the media projects
the server should be allowed to use. Forward slashes keep Windows paths valid
JSON without double escaping.

Choose exactly one mode:

- `manga-video` for manga, manhwa, or webtoon recap videos.
- `ai-story` for written stories turned into illustrated narration videos.
- `song-video` for generated songs or timed lyrics videos.

To allow a second intentional workspace, repeat both arguments:

```json
"--allow-root", "D:/MediaProjects",
"--allow-root", "E:/SharedMedia"
```

Restart the MCP client after changing the mode, checkout path, or allowed
roots.

## Globally installed command

If `mediaconductor` is installed globally and available on `PATH`, the shorter
entry is:

```json
"media-conductor": {
  "command": "mediaconductor",
  "args": [
    "mcp",
    "--mode",
    "manga-video",
    "--allow-root",
    "D:/MediaProjects"
  ]
}
```

## Verify the server command

Run the command outside the MCP client to confirm that the selected mode is
available:

```powershell
uv --project D:/MediaConductor run mediaconductor modes --mode manga-video --json
```

The MCP server communicates over standard input/output, so it normally waits
silently when started by hand. Long-running MCP operations should use the
typed `job_start` tool and then poll with `job_status`.

In `manga-video` mode, the audio, render, join, and full-pipeline MCP tools
require `"manual_review_confirmed": true`. Set it only after a vision-capable
reviewer has opened every original page/strip overlay, every actual crop, and
every panel/narration pairing. MAGI-v3 confidence, DeepSeek-OCR2 output, or the
existence of review sheets does not satisfy that assertion.

The manga-mode `youtube_upload` tool likewise requires
`"final_video_review_confirmed": true`, which may be set only after a complete
normal-speed watch/listen pass of the final export.
