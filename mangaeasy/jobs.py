"""mangaeasy.jobs — detached background jobs with a queryable state file.

Almost every real mangaEasy step runs for minutes to hours (TTS, panel
detection, OCR, renders, uploads). Blocking a caller — an MCP tools/call, a
script, an agent's foreground shell — for that long is the wrong shape, and
"spawn it yourself and forensically infer liveness from log mtimes and
nvidia-smi" was the documented workaround. This module replaces that:

    mangaeasy job-start video --project-root library/X --items 01-12
    -> {"ok": true, "job_id": "20260714-153000-video", ...}   (returns instantly)
    mangaeasy job-status 20260714-153000-video --json
    -> status running/succeeded/failed/orphaned, exit code, last
       MANGAEASY_PROGRESS marker, parsed MANGAEASY_RESULT, log tail
    mangaeasy jobs --json
    -> every job, newest first

How it works: `job-start` writes `<jobs-dir>/<id>.json` and spawns a detached
supervisor (`job-run`, internal) which runs the real command with its output
redirected to `<id>.log`, then records the exit code and the final
MANGAEASY_RESULT payload into the state file. Because the *supervisor* owns
the final write, `job-status` can report a truthful exit code after the fact;
if the supervisor pid is gone without a final write (machine slept, kill -9),
the job is reported `orphaned` rather than forever "running".

Jobs dir: `<work-dir>/jobs` (MANGAEASY_JOBS_DIR overrides). State files are
small JSON; logs are plain text. Both are safe to delete when a job is done.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from mangaeasy.runtime import cli_command, popen_kwargs
from mangaeasy.video_pipeline.common import DEFAULT_WORK_DIR

# Commands a job must not wrap: the server (never terminates), and the job
# commands themselves (recursion).
_DENYLIST = {"mcp", "job-start", "job-run", "job-status", "jobs"}

_TAIL_DEFAULT = 20
_STILL_ACTIVE = 259  # Windows GetExitCodeProcess sentinel


def jobs_dir() -> Path:
    configured = os.environ.get("MANGAEASY_JOBS_DIR")
    if configured:
        return Path(configured)
    return DEFAULT_WORK_DIR / "jobs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _detached_popen_kwargs() -> dict:
    """Survive the parent's death: new session (POSIX) / detached process (Windows)."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _scan_log_markers(log_path: Path) -> tuple[str | None, dict | None]:
    """(last MANGAEASY_PROGRESS line, parsed MANGAEASY_RESULT payload) from the log."""
    progress = None
    result = None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    for line in text.splitlines():
        if line.startswith("MANGAEASY_PROGRESS "):
            progress = line[len("MANGAEASY_PROGRESS "):].strip()
        elif line.startswith("MANGAEASY_RESULT "):
            try:
                result = json.loads(line[len("MANGAEASY_RESULT "):])
            except ValueError:
                pass
    return progress, result


def _effective_status(state: dict) -> str:
    """The trustworthy status: a 'running' job whose supervisor died is orphaned."""
    status = state.get("status", "unknown")
    if status in ("starting", "running") and not _pid_alive(state.get("supervisor_pid")):
        return "orphaned"
    return status


# ── job-start ────────────────────────────────────────────────────────────────

def start_main() -> int:
    parser = argparse.ArgumentParser(
        description="Run any mangaeasy command as a detached background job. "
                    "Prints exactly one JSON object: the job id to poll with job-status.")
    parser.add_argument("command", help="The mangaeasy command to run, e.g. 'video'.")
    parser.add_argument("args", nargs=argparse.REMAINDER,
                        help="Arguments passed through to the command verbatim.")
    parser.add_argument("--jobs-dir", type=Path, default=None,
                        help="Where job state/log files live (default: <work>/jobs).")
    args = parser.parse_args()

    from mangaeasy.cli import COMMANDS  # late import: cli imports nothing heavy

    command = args.command
    if command not in COMMANDS:
        print(json.dumps({"ok": False, "error": f"unknown command: {command}"}))
        return 2
    if command in _DENYLIST:
        print(json.dumps({"ok": False, "error": f"'{command}' cannot run as a job"}))
        return 2

    base = args.jobs_dir or jobs_dir()
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_id = f"{stamp}-{command}"
    n = 1
    while (base / f"{job_id}.json").exists():
        n += 1
        job_id = f"{stamp}-{command}-{n}"
    state_file = base / f"{job_id}.json"
    log_file = base / f"{job_id}.log"

    state = {
        "id": job_id,
        "command": command,
        "args": list(args.args),
        "status": "starting",
        "started_at": _now_iso(),
        "log": str(log_file.resolve()),
        "state_file": str(state_file.resolve()),
        "supervisor_pid": None,
        "child_pid": None,
        "exit_code": None,
    }
    _save_state(state_file, state)

    supervisor = subprocess.Popen(
        cli_command("job-run", str(state_file.resolve())),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_detached_popen_kwargs(),
    )
    # Wait briefly for the supervisor to claim the state file, so the caller's
    # very next job-status doesn't race a still-empty record.
    for _ in range(50):
        current = _load_state(state_file)
        if current.get("supervisor_pid"):
            state = current
            break
        if supervisor.poll() is not None:
            break
        time.sleep(0.1)

    print(json.dumps({
        "ok": True, "job_id": job_id, "command": command,
        "state_file": str(state_file.resolve()), "log": str(log_file.resolve()),
        "poll": f"mangaeasy job-status {job_id} --json",
    }, ensure_ascii=False))
    return 0


# ── job-run (internal supervisor) ────────────────────────────────────────────

def run_main() -> int:
    parser = argparse.ArgumentParser(description="(internal) job-start's supervisor.")
    parser.add_argument("state_file", type=Path)
    args = parser.parse_args()

    state = _load_state(args.state_file)
    state["supervisor_pid"] = os.getpid()
    state["status"] = "running"
    _save_state(args.state_file, state)

    log_path = Path(state["log"])
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        child = subprocess.Popen(
            cli_command(state["command"], *state["args"]),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            **popen_kwargs(),
        )
        state["child_pid"] = child.pid
        _save_state(args.state_file, state)
        rc = child.wait()

    _progress, result = _scan_log_markers(log_path)
    state["status"] = "succeeded" if rc == 0 else "failed"
    state["exit_code"] = rc
    state["finished_at"] = _now_iso()
    if result is not None:
        state["result"] = result
    _save_state(args.state_file, state)
    return 0


# ── job-status ───────────────────────────────────────────────────────────────

def _status_report(state_file: Path, tail: int) -> dict:
    state = _load_state(state_file)
    status = _effective_status(state)
    log_path = Path(state.get("log", ""))
    progress, result = _scan_log_markers(log_path)
    report = {
        "ok": status == "succeeded" or status == "running" or status == "starting",
        "id": state.get("id"),
        "command": state.get("command"),
        "args": state.get("args"),
        "status": status,
        "exit_code": state.get("exit_code"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "progress": progress,
        "result": state.get("result", result),
        "log": state.get("log"),
    }
    if tail > 0 and log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        report["log_tail"] = lines[-tail:]
    return report


def status_main() -> int:
    parser = argparse.ArgumentParser(
        description="Status of one background job started by job-start.")
    parser.add_argument("job_id", help="Job id (or a path to its state file).")
    parser.add_argument("--tail", type=int, default=_TAIL_DEFAULT,
                        help=f"Log tail lines to include (default {_TAIL_DEFAULT}).")
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args()

    candidate = Path(args.job_id)
    if candidate.suffix == ".json" and candidate.exists():
        state_file = candidate
    else:
        state_file = (args.jobs_dir or jobs_dir()) / f"{args.job_id}.json"
    if not state_file.exists():
        message = {"ok": False, "error": f"no such job: {args.job_id}"}
        print(json.dumps(message) if args.as_json else f"[job-status] {message['error']}")
        return 1

    report = _status_report(state_file, args.tail)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"{report['id']}: {report['status']}"
              + (f" (exit {report['exit_code']})" if report["exit_code"] is not None else ""))
        if report.get("progress"):
            print(f"  progress: {report['progress']}")
        for line in report.get("log_tail", []):
            print(f"  | {line}")
    return 0


# ── jobs (list) ──────────────────────────────────────────────────────────────

def list_main() -> int:
    parser = argparse.ArgumentParser(description="List background jobs, newest first.")
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args()

    base = args.jobs_dir or jobs_dir()
    entries = []
    if base.is_dir():
        for state_file in sorted(base.glob("*.json"), reverse=True):
            try:
                state = _load_state(state_file)
            except (OSError, ValueError):
                continue
            entries.append({
                "id": state.get("id", state_file.stem),
                "command": state.get("command"),
                "status": _effective_status(state),
                "exit_code": state.get("exit_code"),
                "started_at": state.get("started_at"),
                "finished_at": state.get("finished_at"),
            })
    if args.as_json:
        print(json.dumps({"ok": True, "jobs_dir": str(base.resolve()), "jobs": entries},
                         ensure_ascii=False))
    else:
        if not entries:
            print(f"[jobs] none under {base}")
        for entry in entries:
            print(f"{entry['id']:<44} {entry['status']:<10} {entry['command']}")
    return 0
