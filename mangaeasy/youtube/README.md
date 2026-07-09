# mangaeasy/youtube — publish to YouTube

The **publish** stage: connect a channel once, then upload (and, if needed,
delete) finished videos. See [docs/youtube.md](../../docs/youtube.md) for the
one-time Google Cloud setup.

## Files

| File | Command | Role |
|---|---|---|
| [`auth.py`](auth.py) | `youtube-auth`, `youtube-status`, `youtube-logout` | OAuth connect flow + status; the google-auth imports live here (lazy) |
| [`upload.py`](upload.py) | `youtube-upload` | resumable upload, hand-rolled `requests` against the resumable protocol |
| [`delete.py`](delete.py) | `youtube-delete` | delete a video (two-step: needs `--confirm`) |
| [`store.py`](store.py) | — | on-disk layout (`<home>/youtube/{client_secret,token,channel}.json`), **plain-JSON helpers only** |

## Gotchas (all load-bearing — see CLAUDE.md)

- **Tokens are secrets**: print paths/booleans, never contents.
- **Upload is hand-rolled `requests`** against the resumable protocol, not the
  Google discovery client — keeps the frozen build small and deps shallow.
  Keep it that way.
- **Default privacy stays `private`**: YouTube force-locks uploads from
  unaudited API projects to private regardless of the request — don't "fix" it.
- `store.SCOPES` requests **full video management** (`youtube.force-ssl`) so a
  bad take can be deleted/replaced via the API. Tokens minted before that
  upload fine but 403 on delete/update — the fix is re-running `youtube-auth`
  (re-consent), not code.
- `youtube-upload --json` prints its JSON object as the **last** stdout line
  (after `MANGAEASY_RESULT`) because the MCP server parses the final line.

## Tests

[tests/test_youtube.py](../../tests/test_youtube.py).
