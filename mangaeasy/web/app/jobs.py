"""mangaeasy.web.app.jobs — subprocess job and editor process management."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterator

from mangaeasy.runtime import cli_command, popen_kwargs
from mangaeasy.web.app.state import log, state


def job_running() -> bool:
    job = state["job"]
    return bool(job and job["thread"].is_alive())


def job_info() -> dict | None:
    job = state["job"]
    if not job:
        return None
    return {"kind": job["kind"], "name": job["name"], "running": job["thread"].is_alive()}


def iter_lines(stream) -> Iterator[str]:
    """Read a binary stdout stream and yield complete, non-empty lines.

    Bare \\r (tqdm / FFmpeg progress-bar overwrite) is handled by keeping
    only the text after the last \\r on each \\n-terminated line, so
    intermediate progress frames are silently discarded.  \\r\\n Windows
    line endings are handled correctly.
    """
    buf = b""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            # \r\n → proper Windows newline: strip trailing \r
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            # bare \r inside line → progress overwrite: keep last segment only
            elif b"\r" in raw:
                raw = raw.rsplit(b"\r", 1)[1]
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                yield line
    # flush any remaining bytes (no trailing newline)
    if buf.strip():
        line = buf.replace(b"\r", b"").decode("utf-8", errors="replace").rstrip()
        if line:
            yield line


def spawn_cli(command: str, args: list[str], cwd: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["MANGAEASY_PROJECT_ROOT"] = str(cwd)
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Force UTF-8 I/O so subprocess print() calls with non-ASCII characters
    # (arrows, checkmarks, …) don't crash on Windows where the default is cp1252.
    env["PYTHONIOENCODING"] = "utf-8"
    # Signal to child processes that they're running inside the desktop app so
    # Flask-based editor tools emit MANGAEASY_OPEN_URL instead of calling
    # webbrowser.open() (which would open the OS browser instead of the app).
    env["MANGAEASY_APP_MODE"] = "1"
    full = cli_command(command, *args)
    log(f"$ mangaeasy {command} {' '.join(args)}")
    return subprocess.Popen(
        full,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        # Binary mode — iter_lines handles \r/\r\n/\n and UTF-8 decoding.
        **popen_kwargs(),
    )


def pump(proc: subprocess.Popen, label: str) -> None:
    assert proc.stdout is not None
    for line in iter_lines(proc.stdout):
        log(line)
    code = proc.wait()
    log(f"[{label}] finished with exit code {code}")


def cleanup() -> None:
    job = state["job"]
    if job and job.get("proc") and job["proc"].poll() is None:
        job["proc"].terminate()
    for proc in state["editors"].values():
        if proc.poll() is None:
            proc.terminate()
