"""mangaeasy.utils — shared utilities."""

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile


def emit_result(**payload) -> None:
    """Print the machine-parsable result marker line.

    Artifact-producing commands end a completed or review-required run with one
    ``MANGAEASY_RESULT {...json...}`` line so scripts and AI agents can find
    the produced files without scraping human log text — same family as the
    ``MANGAEASY_PROGRESS n/m`` and ``MANGAEASY_OPEN_URL`` markers. Keep the
    payload JSON on a single line; Paths are stringified automatically.
    """
    from mangaeasy.brand import RESULT_MARKERS

    print(RESULT_MARKERS[0] + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def parse_result_marker(line: str) -> dict | None:
    """Parse one output line as a result marker, accepting legacy spellings.

    Tool scripts copied into existing external envs still print the old
    ``MEDIACONDUCTOR_RESULT`` prefix; every scanner must keep understanding both.
    """
    from mangaeasy.brand import RESULT_MARKERS

    for marker in RESULT_MARKERS:
        if line.startswith(marker):
            try:
                payload = json.loads(line[len(marker):])
            except ValueError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def numeric_sort_key(path: "Path | str") -> list:
    """Natural-sort key: extracts all integers from a filename stem.

    Works on Path objects or plain strings.  Files with no digits sort last.
    """
    stem = Path(path).stem
    nums = re.findall(r"\d+", stem)
    return [int(n) for n in nums] if nums else [float("inf")]


def next_archive_run_dir(old_root: Path) -> Path:
    """Allocate and create the next unused old_root/run_NNNN/ folder.

    Scans whatever run_NNNN folders already exist so any number of past runs
    can stack up without colliding or clobbering each other.
    """
    old_root.mkdir(parents=True, exist_ok=True)
    existing = [
        int(match.group(1))
        for entry in old_root.iterdir()
        if entry.is_dir() and (match := re.fullmatch(r"run_(\d+)", entry.name))
    ]
    next_run = (max(existing) + 1) if existing else 1
    run_dir = old_root / f"run_{next_run:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def archive_into_run(path: Path, run_dir: Path, *, subdir: str | None = None) -> Path | None:
    """Move an existing file into run_dir (optionally nested under subdir), preserving its name."""
    if not path.exists():
        return None
    destination_dir = (run_dir / subdir) if subdir else run_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / path.name
    shutil.move(str(path), str(destination))
    return destination


class LazyArchiveRunDir:
    """Allocates a single run_NNNN/ folder the first time it's actually needed.

    Audio generation may run for many items without ever overwriting an
    existing file, so eagerly creating an empty old/run_NNNN/ on every
    invocation would litter the project with empty runs. This defers
    `next_archive_run_dir` until the first archive actually happens, then
    reuses that same folder for the rest of the run.
    """

    def __init__(self, old_root: Path) -> None:
        self._old_root = old_root
        self._dir: Path | None = None

    @property
    def dir(self) -> Path:
        if self._dir is None:
            self._dir = next_archive_run_dir(self._old_root)
        return self._dir

    @property
    def allocated(self) -> Path | None:
        return self._dir


def archive_before_overwrite(path: Path) -> Path | None:
    """Move an existing output file into <path's folder>/old/run_NNNN/ before it gets overwritten.

    Re-running a generation step would otherwise silently replace the last
    result. Each call allocates its own run_NNNN folder, which is right for a
    single output file (item video, long video, chapter video) generated
    once per invocation.
    """
    if not path.exists():
        return None
    run_dir = next_archive_run_dir(path.parent / "old")
    return archive_into_run(path, run_dir)


def remove_tree(path: Path, *, ignore_errors: bool = False) -> None:
    """``shutil.rmtree`` that also succeeds on Windows read-only files.

    POSIX decides whether a file can be unlinked from its *directory's*
    permissions, so a read-only file inside a writable folder deletes fine. On
    Windows the read-only attribute is on the file itself and ``DeleteFile``
    refuses it outright, so ``shutil.rmtree`` raises ``PermissionError``
    partway through — leaving `workspace-reset` and the `video-clean-*`
    commands with a half-erased tree and a traceback, which is exactly the
    state those commands exist to avoid. Clearing the attribute and retrying
    the one failed entry is the documented fix; on Linux and macOS this
    handler is simply never reached.
    """
    if ignore_errors:
        shutil.rmtree(path, ignore_errors=True)
        return

    def _retry(function, failed_path, _exc_info):
        """Clear the read-only bit and retry the one operation that failed.

        Re-raises when that does not help, so a genuinely undeletable tree
        (a file held open by another process) still reports the real error
        rather than silently leaving files behind.
        """
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)
    # onexc replaced onerror in 3.12; this project supports 3.10+.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


def atomic_write_json(path: Path, data: "dict | list") -> bool:
    """Write data as JSON to path atomically (tmp + rename)."""
    try:
        with NamedTemporaryFile("w", dir=str(path.parent), delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            tmpname = tf.name
        os.replace(tmpname, str(path))
        return True
    except Exception as exc:
        print(f"[error] Failed to write config: {exc}")
        try:
            if "tmpname" in locals():
                os.remove(tmpname)
        except Exception:
            pass
        return False
