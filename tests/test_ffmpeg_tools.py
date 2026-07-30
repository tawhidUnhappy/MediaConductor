from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mangaeasy.video_pipeline import make_long_video, make_videos, run_pipeline
from mangaeasy.video_pipeline import ffmpeg_tools
from mangaeasy.video_pipeline.ffmpeg_tools import h264_encoder_args
from mangaeasy.video_pipeline.item_video_builder import VideoBuildConfig
from mangaeasy.video_pipeline.long_video_builder import LongVideoConfig


@pytest.mark.parametrize(
    ("portable", "x264"),
    [
        ("p1", "ultrafast"),
        ("p2", "superfast"),
        ("p3", "veryfast"),
        ("p4", "fast"),
        ("p5", "medium"),
        ("p6", "slow"),
        ("p7", "veryslow"),
    ],
)
def test_nvenc_style_presets_map_to_valid_libx264_presets(portable: str, x264: str):
    assert h264_encoder_args("libx264", portable, 18) == [
        "-c:v", "libx264", "-preset", x264, "-crf", "18",
    ]


@pytest.mark.parametrize("preset", ["ultrafast", "medium", "slow", "veryslow"])
def test_native_libx264_presets_pass_through(preset: str):
    assert h264_encoder_args("libx264", preset, 20) == [
        "-c:v", "libx264", "-preset", preset, "-crf", "20",
    ]


def test_nvenc_keeps_portable_quality_preset():
    assert h264_encoder_args("h264_nvenc", "p5", 18) == [
        "-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
        "-rc", "vbr", "-cq", "18", "-b:v", "0",
    ]


def test_video_build_config_uses_production_quality_defaults(tmp_path: Path):
    config = VideoBuildConfig(
        project_root=tmp_path / "library",
        audio_root=tmp_path / "audio",
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
    )
    assert config.preset == "p5"
    assert config.audio_bitrate == "192k"


def test_long_video_config_uses_production_quality_defaults(tmp_path: Path):
    config = LongVideoConfig(
        project_root=tmp_path / "library",
        output_root=tmp_path / "output",
        work_dir=tmp_path / "work",
    )
    assert config.preset == "p5"
    assert config.audio_bitrate == "192k"


@pytest.mark.parametrize(
    ("parser", "preset_attribute"),
    [
        (make_videos.parse_args, "preset"),
        (make_long_video.parse_args, "preset"),
        (run_pipeline.parse_args, "video_preset"),
    ],
)
def test_video_cli_parsers_use_production_quality_defaults(
    monkeypatch, parser, preset_attribute: str,
):
    monkeypatch.setattr(sys, "argv", ["mangaeasy-video-test"])
    args = parser()
    assert getattr(args, preset_attribute) == "p5"
    assert args.audio_bitrate == "192k"


# ── Encoder selection must survive an unusable hardware encoder ───────────────

def test_auto_falls_back_when_a_hardware_encoder_cannot_open(monkeypatch):
    """`ffmpeg -encoders` lists what was compiled in, not what can be used.

    The vendored FFmpeg is a rolling master build, so it can require a newer
    NVENC API than the installed driver offers ("Required: 13.1 Found: 13.0").
    Selection saw h264_nvenc in the list, chose it, and every render died on
    the first segment — on a machine whose libx264 path was fine.
    """
    ffmpeg_tools.available_encoders.cache_clear()
    ffmpeg_tools.encoder_works.cache_clear()
    ffmpeg_tools.choose_h264_encoder.cache_clear()
    monkeypatch.setattr(ffmpeg_tools, "available_encoders",
                        lambda: {"h264_nvenc", "libx264"})
    monkeypatch.setattr(ffmpeg_tools, "encoder_works", lambda name: name == "libx264")
    try:
        assert ffmpeg_tools.choose_h264_encoder("auto") == "libx264"
    finally:
        ffmpeg_tools.choose_h264_encoder.cache_clear()


def test_auto_uses_a_hardware_encoder_that_does_open(monkeypatch):
    ffmpeg_tools.choose_h264_encoder.cache_clear()
    monkeypatch.setattr(ffmpeg_tools, "available_encoders",
                        lambda: {"h264_nvenc", "libx264"})
    monkeypatch.setattr(ffmpeg_tools, "encoder_works", lambda name: True)
    try:
        assert ffmpeg_tools.choose_h264_encoder("auto") == "h264_nvenc"
    finally:
        ffmpeg_tools.choose_h264_encoder.cache_clear()


def test_an_explicit_encoder_is_never_silently_substituted(monkeypatch):
    """Naming an encoder must not be overridden — that would hide a real
    misconfiguration behind a mysteriously slow render."""
    ffmpeg_tools.choose_h264_encoder.cache_clear()
    monkeypatch.setattr(ffmpeg_tools, "encoder_works", lambda name: False)
    try:
        assert ffmpeg_tools.choose_h264_encoder("h264_nvenc") == "h264_nvenc"
    finally:
        ffmpeg_tools.choose_h264_encoder.cache_clear()


def test_encoder_probe_reports_libx264_usable_on_this_machine():
    """libx264 is the guaranteed fallback; if it cannot open, nothing renders.

    Resolves ffmpeg the way the CLI does — via the vendored bin dir — so this
    exercises the portable binary the install actually ships with, not just
    whatever happens to be on the developer's PATH.
    """
    import shutil as _shutil

    from mangaeasy.tools.vendored import ensure_vendored_path

    ensure_vendored_path()
    if not _shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available (run `mangaeasy bootstrap-tools`)")
    ffmpeg_tools.encoder_works.cache_clear()
    assert ffmpeg_tools.encoder_works("libx264") is True
    assert ffmpeg_tools.encoder_works("definitely_not_an_encoder") is False


def test_filter_script_probe_answers_for_the_real_ffmpeg():
    """Whichever spelling this ffmpeg takes, the probe must agree with it."""
    import shutil as _shutil

    from mangaeasy.tools.vendored import ensure_vendored_path

    ensure_vendored_path()
    if not _shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not available (run `mangaeasy bootstrap-tools`)")
    ffmpeg_tools.supports_filter_complex_script.cache_clear()
    flag = ffmpeg_tools.filter_script_args(Path("g.filter"))[0]
    assert flag in ("-filter_complex_script", "-/filter_complex")
    # And that flag really is accepted by this build.
    from mangaeasy import runtime

    result = runtime.run(["ffmpeg", "-hide_banner", "-h", "full"],
                         check=False, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if flag == "-filter_complex_script":
        assert "-filter_complex_script" in (result.stdout or "")


# ── Long filter graphs must travel as a file on every ffmpeg version ─────────

def test_filter_script_args_uses_a_flag_this_ffmpeg_accepts(monkeypatch):
    """FFmpeg 8 removed -filter_complex_script for -/filter_complex.

    Both spellings must keep working: the vendored build is rolling master
    (new spelling only), while a distro/Homebrew ffmpeg may be 6.x or 7.x
    (old spelling only). Passing the wrong one aborts with "Unrecognized
    option" before any work happens.
    """
    script = Path("graph.filter")

    monkeypatch.setattr(ffmpeg_tools, "supports_filter_complex_script", lambda: True)
    assert ffmpeg_tools.filter_script_args(script) == ["-filter_complex_script", "graph.filter"]

    monkeypatch.setattr(ffmpeg_tools, "supports_filter_complex_script", lambda: False)
    assert ffmpeg_tools.filter_script_args(script) == ["-/filter_complex", "graph.filter"]


def test_filter_script_args_never_emits_the_inline_flag(monkeypatch):
    """`-filter_complex` inline is what blows the Windows 32,767-char argv limit."""
    for supported in (True, False):
        monkeypatch.setattr(ffmpeg_tools, "supports_filter_complex_script",
                            lambda supported=supported: supported)
        assert "-filter_complex" not in ffmpeg_tools.filter_script_args(Path("g.filter"))
