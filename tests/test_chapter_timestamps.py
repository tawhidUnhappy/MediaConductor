"""YouTube chapter timestamps generated from rendered item videos."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mediaconductor.video_pipeline import chapter_timestamps


def _project(tmp_path: Path, *items: str, name: str = "Series") -> tuple[Path, Path]:
    project_root = tmp_path / name
    output_root = tmp_path / "output"
    for item in items:
        (project_root / item / "panels").mkdir(parents=True)
        video = output_root / name / "items" / f"item_{item}.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.touch()
    return project_root, output_root


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00"),
        (65.99, "01:05"),
        (3599.99, "59:59"),
        (3600, "1:00:00"),
        (36_601.8, "10:10:01"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert chapter_timestamps.format_timestamp(seconds) == expected


@pytest.mark.parametrize("seconds", [-1, float("inf"), float("nan")])
def test_format_timestamp_rejects_invalid_values(seconds):
    with pytest.raises(ValueError, match="finite non-negative"):
        chapter_timestamps.format_timestamp(seconds)


def test_report_uses_source_order_exact_names_and_cumulative_durations(tmp_path):
    project_root, output_root = _project(tmp_path, "10", "2.1", "01", "02", "9.5")
    durations = {
        "item_01.mp4": 65.5,
        "item_02.mp4": 120.25,
        "item_2.1.mp4": 3414.75,
        "item_9.5.mp4": 60.0,
        "item_10.mp4": 10.0,
    }

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        allow_gaps=True,
        duration_probe=lambda path: durations[path.name],
    )

    assert [entry["item"] for entry in report["entries"]] == ["01", "02", "2.1", "9.5", "10"]
    assert [entry["title"] for entry in report["entries"]] == [
        "Chapter 01",
        "Chapter 02",
        "Chapter 2.1",
        "Chapter 9.5",
        "Chapter 10",
    ]
    assert [entry["timestamp"] for entry in report["entries"]] == [
        "00:00",
        "01:05",
        "03:05",
        "1:00:00",
        "1:01:00",
    ]
    assert report["total_duration_seconds"] == 3670.5
    assert report["total_duration"] == "1:01:10"


def test_items_and_item_range_use_common_selection_rules(tmp_path):
    project_root, output_root = _project(tmp_path, "01", "02", "2.1", "03", "04")

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        items=["2.1"],
        item_range="03-04",
        duration_probe=lambda _path: 10,
    )

    # video-join treats selected endpoints as one inclusive value range while
    # preserving an exact decimal lower endpoint.
    assert [entry["item"] for entry in report["entries"]] == ["2.1", "03", "04"]


def test_missing_rendered_videos_are_listed_before_probing(tmp_path):
    project_root, output_root = _project(tmp_path, "01", "02", "03")
    (output_root / "Series" / "items" / "item_02.mp4").unlink()
    (output_root / "Series" / "items" / "item_03.mp4").unlink()
    probed: list[Path] = []

    with pytest.raises(FileNotFoundError) as exc_info:
        chapter_timestamps.build_chapter_report(
            project_root=project_root,
            output_root=output_root,
            item_range="01-03",
            duration_probe=lambda path: probed.append(path) or 10,
        )

    message = str(exc_info.value)
    assert "Missing rendered item video(s)" in message
    assert "02" in message
    assert "03" in message
    assert probed == []


def test_range_includes_decimal_render_just_like_video_join(tmp_path):
    project_root, output_root = _project(tmp_path, "01", "02", "2.1", "03")

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        item_range="01-03",
        duration_probe=lambda _path: 10,
    )

    assert [entry["item"] for entry in report["entries"]] == ["01", "02", "2.1", "03"]


def test_exact_decimal_selection_matches_video_join(tmp_path):
    project_root, output_root = _project(tmp_path, "09", "9.5", "10")

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        items=["9.5"],
        duration_probe=lambda _path: 10,
    )

    assert [entry["item"] for entry in report["entries"]] == ["9.5"]


def test_sparse_item_endpoints_include_rendered_items_between_them(tmp_path):
    project_root, output_root = _project(tmp_path, "01", "02", "03")

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        items=["01", "03"],
        duration_probe=lambda _path: 10,
    )

    assert [entry["item"] for entry in report["entries"]] == ["01", "02", "03"]


def test_allow_gaps_reports_and_skips_genuinely_absent_integer_item(tmp_path):
    project_root, output_root = _project(tmp_path, "01", "03")

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        item_range="01-03",
        allow_gaps=True,
        duration_probe=lambda _path: 10,
    )

    assert [entry["item"] for entry in report["entries"]] == ["01", "03"]
    assert report["gaps"] == ["02"]


def test_legacy_chapters_directory_matches_video_join_fallback(tmp_path):
    project_root = tmp_path / "Series"
    (project_root / "01").mkdir(parents=True)
    output_root = tmp_path / "output"
    legacy = output_root / "Series" / "chapters" / "chapter_01.mp4"
    legacy.parent.mkdir(parents=True)
    legacy.touch()

    report = chapter_timestamps.build_chapter_report(
        project_root=project_root,
        output_root=output_root,
        duration_probe=lambda _path: 10,
    )

    assert [entry["video"] for entry in report["entries"]] == [str(legacy.resolve())]


@pytest.mark.parametrize("duration", [0, -0.1, float("inf"), "not-a-number"])
def test_invalid_probed_duration_fails_with_video_path(tmp_path, duration):
    project_root, output_root = _project(tmp_path, "01")

    with pytest.raises(RuntimeError, match=r"item_01\.mp4"):
        chapter_timestamps.build_chapter_report(
            project_root=project_root,
            output_root=output_root,
            duration_probe=lambda _path: duration,
        )


def test_probe_video_duration_uses_runtime_and_parses_stdout(tmp_path, monkeypatch):
    video = tmp_path / "item_01.mp4"
    video.touch()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="12.75\n", stderr="")

    monkeypatch.setattr(chapter_timestamps.runtime, "run", fake_run)

    assert chapter_timestamps.probe_video_duration(video) == 12.75
    assert calls[0][0][0] == "ffprobe"
    assert calls[0][0][calls[0][0].index("-select_streams") + 1] == "v:0"
    assert calls[0][0][calls[0][0].index("-show_entries") + 1] == "stream=duration"
    assert calls[0][0][-1] == str(video)
    assert calls[0][1] == {"capture_output": True, "text": True, "check": True}


def test_probe_video_duration_reports_ffprobe_failure(tmp_path, monkeypatch):
    video = tmp_path / "item_01.mp4"
    video.touch()

    def fake_run(argv, **_kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="invalid data")

    monkeypatch.setattr(chapter_timestamps.runtime, "run", fake_run)

    with pytest.raises(RuntimeError, match=r"item_01\.mp4: invalid data"):
        chapter_timestamps.probe_video_duration(video)


def test_human_main_is_ready_to_paste_without_machine_marker(tmp_path, monkeypatch, capsys):
    project_root, output_root = _project(tmp_path, "01", "02")
    monkeypatch.setattr(chapter_timestamps, "probe_video_duration", lambda _path: 65)

    assert chapter_timestamps.main([
        "--project-root", str(project_root),
        "--output-root", str(output_root),
    ]) == 0

    assert capsys.readouterr().out == "00:00 Chapter 01\n01:05 Chapter 02\n"


def test_json_main_emits_one_clean_document(tmp_path, monkeypatch, capsys):
    project_root, output_root = _project(tmp_path, "01", "02", "2.1", "03")
    monkeypatch.setattr(chapter_timestamps, "probe_video_duration", lambda _path: 30.5)

    assert chapter_timestamps.main([
        "--project-root", str(project_root),
        "--output-root", str(output_root),
        "--item-range", "01-03",
        "--json",
    ]) == 0

    output = capsys.readouterr().out
    assert "MEDIACONDUCTOR_RESULT" not in output
    report = json.loads(output)
    assert [entry["item"] for entry in report["entries"]] == ["01", "02", "2.1", "03"]
    assert report["total_duration_seconds"] == 122.0
    assert report["total_duration"] == "02:02"
    assert report["gaps"] == []
