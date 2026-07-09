# mangaeasy/utils — shared helpers (archive, result markers, JSON)

Small, dependency-light helpers imported across the pipeline. This is a
**library package** (no commands of its own). `__init__.py` is the whole
public surface.

## Public API (`mangaeasy.utils`)

| Function | Role |
|---|---|
| `emit_result(**payload)` | print the final `MANGAEASY_RESULT {...}` line every generation command must emit (part of the CLI contract) |
| `archive_before_overwrite(path)` | move an existing generated file into `old/run_NNNN/` before it's overwritten — **never silently destroy output** |
| `next_archive_run_dir(old_root)` / `archive_into_run(...)` / `LazyArchiveRunDir` | the run-numbered archive machinery the above is built on |
| `numeric_sort_key(path)` | human/numeric sort for item and page names |
| `atomic_write_json(path, data)` | crash-safe JSON write (temp file + rename) |

## Why it matters

- **Archive-before-overwrite is a project invariant.** Any new code that
  overwrites generated audio/video must go through `archive_before_overwrite()`
  / `archive_into_run()` — don't `write_bytes()` over an existing file. See
  [CLAUDE.md](../../CLAUDE.md) ("Archive-before-overwrite").
- `emit_result()` is required by the machine-readable CLI contract — new
  generation commands must call it as their last line.

## Tests

[tests/test_archive.py](../../tests/test_archive.py).
