# MediaConductor MCP configuration

The examples below run the source checkout at `D:/MediaConductor` and allow it
to access media only under `D:/MediaProjects`.

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

`--mode manga-video` is accepted for client-config compatibility and is the
default; `manga-video` is the only catalog. There is no router mode and no
`--all-tools` escape hatch — a tool outside the catalog answers *unknown*.

To allow a second intentional workspace, repeat both arguments:

```json
"--allow-root", "D:/MediaProjects",
"--allow-root", "E:/SharedMedia"
```

Restart the MCP client after changing the checkout path or allowed roots.

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

Run the command outside the MCP client to confirm the catalog is available:

```powershell
uv --project D:/MediaConductor run mediaconductor modes --mode manga-video --json
```

The MCP server communicates over standard input/output, so it normally waits
silently when started by hand. Long-running MCP operations should use the
typed `job_start` tool and then poll with `job_status`.

## Review gates

There is no confirmation argument to set. The audio, render, join, and
full-pipeline tools verify hash-bound review records themselves and refuse to
run without current ones; `youtube_upload` additionally requires a current
final-video record for the exact file plus a complete rights manifest.

Record approvals with the `manga_review` tool after the corresponding visual
pass:

```json
{"tool": "manga_review", "arguments": {
  "action": "crop", "project_root": "D:/MediaProjects/library/Recap",
  "items": ["01"], "reviewer": "sam"}}
```

Set them only after a vision-capable reviewer has opened every original
page/strip overlay, every actual crop, and every panel/narration pairing —
and, for `final-video`, after a complete normal-speed watch/listen pass of the
final export. MAGI-v3 confidence, DeepSeek-OCR2 output, or the existence of
review sheets does not satisfy that. Because each record is bound to the exact
bytes it covers, a later re-crop, rewrite, or re-encode invalidates it
automatically.
