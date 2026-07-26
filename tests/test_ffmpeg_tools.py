from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mediaconductor.video_pipeline import make_long_video, make_videos, run_pipeline
from mediaconductor.video_pipeline.ffmpeg_tools import h264_encoder_args
from mediaconductor.video_pipeline.item_video_builder import VideoBuildConfig
from mediaconductor.video_pipeline.long_video_builder import LongVideoConfig


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
    monkeypatch.setattr(sys, "argv", ["mediaconductor-video-test"])
    args = parser()
    assert getattr(args, preset_attribute) == "p5"
    assert args.audio_bitrate == "192k"
