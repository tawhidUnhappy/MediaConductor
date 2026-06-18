"""mangaeasy.web.app.jobs — subprocess job and editor process management."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterator

from mangaeasy.runtime import cli_command, popen_kwargs
from mangaeasy.web.app import state as app_state
from mangaeasy.web.app.state import log, state
from mangaeasy.web.flask_utils import terminal_broadcaster

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_COUNT_RE = re.compile(r"(?<!\d)(\d{1,6})\s*/\s*(\d{1,6})(?!\d)")
_PENDING_RE = re.compile(
    r"(\d{1,6})\s+(?:panel(?:\(s\)|s)?|page(?:s)?|file(?:s)?|item(?:s)?|audio|frame(?:s)?|clip(?:s)?)\s+"
    r"(?:pending|to\s+download|to\s+process)",
    re.I,
)
# Pipeline scripts that loop over chapters (batch video/audio rendering) print this
# sentinel once per chapter completed instead of relying on noisy per-file counters
# (TTS clip N/M, render segment N/M) bubbling up as the displayed "overall" progress.
_CHAPTER_RE = re.compile(r"^MANGAEASY_PROGRESS\s+(\d{1,6})/(\d{1,6})(?:\s+(.*))?$")


def _progress_label(line: str, fallback: str) -> str:
    lower = f"{line} {fallback}".lower()
    if "got-ocr" in lower or "ocr" in lower:
        return "OCR panels"
    if "[frame]" in lower or "render" in lower:
        return "Rendering frames"
    if "[pcm]" in lower or "fade" in lower:
        return "Preparing audio"
    if "download" in lower or "skip (exists)" in lower:
        return "Downloading pages"
    if "kokoro" in lower or "tts" in lower or "audio" in lower:
        return "Generating audio"
    if "panel" in lower:
        return "Processing panels"
    return fallback


def report_progress_from_line(line: str, fallback_label: str, job_state: dict | None = None) -> None:
    """Extract simple x/y CLI progress and send it to the app progress bar.

    job_state tracks whether this job has emitted an explicit chapter-level
    MANGAEASY_PROGRESS marker. Once it has, per-file noise (a TTS clip count, a
    render segment count) is ignored so the bar reflects chapters done instead
    of flickering between unrelated counters every line.
    """
    text = _ANSI_RE.sub("", line).strip()
    if not text:
        return

    chapter = _CHAPTER_RE.match(text)
    if chapter:
        if job_state is not None:
            job_state["chapter_mode"] = True
        value, total = int(chapter.group(1)), int(chapter.group(2))
        label = chapter.group(3) or fallback_label
        if total > 0:
            app_state.progress(max(0, min(value, total)), total, label)
        return

    if job_state is not None and job_state.get("chapter_mode"):
        return

    pending = _PENDING_RE.search(text)
    if pending:
        total = int(pending.group(1))
        if total > 0:
            app_state.progress(0, total, _progress_label(text, fallback_label))
        return

    match = _COUNT_RE.search(text)
    if not match:
        return
    value = int(match.group(1))
    total = int(match.group(2))
    if total <= 0:
        return
    app_state.progress(max(0, min(value, total)), total, _progress_label(text, fallback_label))


def _parse_progress_buffer(buffer: bytes, fallback_label: str, job_state: dict | None = None) -> bytes:
    while True:
        positions = [pos for pos in (buffer.find(b"\n"), buffer.find(b"\r")) if pos >= 0]
        if not positions:
            break
        pos = min(positions)
        raw, buffer = buffer[:pos], buffer[pos + 1:]
        line = raw.decode("utf-8", errors="replace").strip()
        if line:
            report_progress_from_line(line, fallback_label, job_state)
    return buffer[-8192:]


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
    log(f"\x1b[2m{'─'*60}\x1b[0m")
    log(f"\x1b[1;36m$ mangaeasy {command} {' '.join(args)}\x1b[0m")
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
    app_state.progress(0, 0, f"Starting {label}")
    job_state: dict = {"chapter_mode": False}
    buffer = b""
    while True:
        chunk = proc.stdout.read(512)
        if not chunk:
            break
        terminal_broadcaster.write_raw(chunk)
        buffer = _parse_progress_buffer(buffer + chunk, label, job_state)
    if buffer.strip():
        report_progress_from_line(buffer.decode("utf-8", errors="replace"), label, job_state)
    code = proc.wait()
    color = "\x1b[32m" if code == 0 else "\x1b[31m"
    app_state.progress(1, 1, f"{label} {'done' if code == 0 else 'failed'}")
    log(f"{color}[{label}] finished (exit {code})\x1b[0m")


def cleanup() -> None:
    job = state["job"]
    if job and job.get("proc") and job["proc"].poll() is None:
        job["proc"].terminate()
    for proc in state["editors"].values():
        if proc.poll() is None:
            proc.terminate()
