"""The narration-concat ffmpeg call must stay inside the OS command-line limit.

Regression: DragonKnight chapter 31 has 164 narrated panels. The filter graph
is ~150 chars per panel, so passing it as a single ``-filter_complex`` argument
produced a ~38,000-char argv and Windows refused to start ffmpeg at all
(``FileNotFoundError: [WinError 206] The filename or extension is too long``).
The whole 46-chapter build failed after rendering 45 chapters.
"""

from pathlib import Path

from mediaconductor.video_pipeline import item_video_builder
from mediaconductor.video_pipeline.item_assets import PanelAsset

# Windows caps a command line at 32,767 characters; stay clear of it.
WINDOWS_COMMAND_LIMIT = 32767


def _assets(count: int, root: Path) -> list[PanelAsset]:
    return [
        PanelAsset(
            image_path=root / "panels" / f"31_{i:03d}_01.jpg",
            audio_path=root / "audio_faded" / "DragonKnight" / "31" / f"31_{i:03d}_01.wav",
            audio_duration=3.0,
            visual_duration=3.0,
            frame_count=72,
        )
        for i in range(1, count + 1)
    ]


def test_long_chapter_stays_under_the_command_line_limit(tmp_path, monkeypatch):
    captured: list[list[str]] = []
    monkeypatch.setattr(item_video_builder, "run", lambda argv, *a, **k: captured.append(argv))

    work_dir = tmp_path / "work"
    item_video_builder.build_item_narration_wav(
        tmp_path / "item",
        _assets(164, tmp_path),
        work_dir,
        work_dir / "31_narration.wav",
    )

    assert len(captured) == 1
    argv = captured[0]
    assert sum(len(part) + 1 for part in argv) < WINDOWS_COMMAND_LIMIT

    # The graph travels as a file, not as an argument.
    assert "-filter_complex_script" in argv
    assert "-filter_complex" not in argv
    script = Path(argv[argv.index("-filter_complex_script") + 1])
    assert script.is_file()

    # And the graph itself is still complete and correct.
    graph = script.read_text(encoding="utf-8")
    assert graph.count("aformat=") == 164 + 1  # one per panel, plus the concat tail
    assert "concat=n=164:v=0:a=1" in graph
    assert graph.rstrip().endswith("[a]")
    assert "-map" in argv and argv[argv.index("-map") + 1] == "[a]"
