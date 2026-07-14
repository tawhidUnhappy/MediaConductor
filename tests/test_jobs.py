"""Background jobs: start -> supervisor -> status lifecycle, and the guards."""

import json
import subprocess
import sys
import time

from mangaeasy.jobs import _effective_status


def run_cli(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mangaeasy.cli", *args],
        capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=cwd,
    )


def test_job_lifecycle(tmp_path):
    jobs_dir = tmp_path / "jobs"
    start = run_cli("job-start", "--jobs-dir", str(jobs_dir), "where", "--json")
    assert start.returncode == 0, start.stderr
    payload = json.loads(start.stdout)
    assert payload["ok"] is True
    job_id = payload["job_id"]
    assert "where" in job_id

    # The supervisor is detached; poll until it records a final state.
    report = None
    for _ in range(60):
        status = run_cli("job-status", job_id, "--jobs-dir", str(jobs_dir), "--json")
        report = json.loads(status.stdout)
        if report["status"] in ("succeeded", "failed", "orphaned"):
            break
        time.sleep(0.5)
    assert report is not None
    assert report["status"] == "succeeded", report
    assert report["exit_code"] == 0
    assert report["log_tail"], "log tail should contain the child's output"

    listing = run_cli("jobs", "--jobs-dir", str(jobs_dir), "--json")
    jobs = json.loads(listing.stdout)["jobs"]
    assert [j["id"] for j in jobs] == [job_id]
    assert jobs[0]["status"] == "succeeded"


def test_job_start_rejects_unknown_and_denylisted(tmp_path):
    jobs_dir = str(tmp_path / "jobs")
    bad = run_cli("job-start", "--jobs-dir", jobs_dir, "not-a-command")
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["ok"] is False

    recursive = run_cli("job-start", "--jobs-dir", jobs_dir, "mcp")
    assert recursive.returncode == 2
    assert json.loads(recursive.stdout)["ok"] is False


def test_job_status_unknown_id(tmp_path):
    missing = run_cli("job-status", "nope", "--jobs-dir", str(tmp_path), "--json")
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["ok"] is False


def test_dead_supervisor_reports_orphaned():
    # A 'running' record whose supervisor pid no longer exists must not be
    # reported as running forever (machine sleep / kill -9).
    state = {"status": "running", "supervisor_pid": 999_999_999}
    assert _effective_status(state) == "orphaned"
    assert _effective_status({"status": "succeeded", "supervisor_pid": None}) == "succeeded"
