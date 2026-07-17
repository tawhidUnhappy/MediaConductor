from __future__ import annotations

import json

from mediaconductor import defaults


def _write_system_config(path, bgm):
    path.write_text(json.dumps({"bgm": bgm}), encoding="utf-8")


def test_default_background_music_uses_explicit_file(tmp_path, monkeypatch):
    cfg = tmp_path / "config.system.json"
    music = tmp_path / "one.wav"
    music.write_bytes(b"wav")
    _write_system_config(cfg, {"file": str(music), "volume_db": -26})
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", cfg)
    assert defaults.default_background_music() == music


def test_default_background_music_picks_first_file_from_directory(tmp_path, monkeypatch):
    cfg = tmp_path / "config.system.json"
    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    (bgm_dir / "b_track.wav").write_bytes(b"b")
    (bgm_dir / "a_track.mp3").write_bytes(b"a")
    _write_system_config(cfg, {"directory": str(bgm_dir), "volume_db": -26})
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", cfg)
    assert defaults.default_background_music() == bgm_dir / "a_track.mp3"


def test_manga_video_audio_defaults_to_faded_eight_ms(tmp_path, monkeypatch):
    cfg = tmp_path / "missing-config.system.json"
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", cfg)

    assert defaults.default_manga_video_audio_source() == "faded"
    assert defaults.default_manga_video_audio_fade_ms() == 8.0


def test_manga_video_audio_defaults_are_configurable(tmp_path, monkeypatch):
    cfg = tmp_path / "config.system.json"
    cfg.write_text(
        json.dumps({"manga_video": {"audio_source": "raw", "audio_fade_ms": 12.5}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", cfg)

    assert defaults.default_manga_video_audio_source() == "raw"
    assert defaults.default_manga_video_audio_fade_ms() == 12.5


def test_invalid_manga_video_audio_config_falls_back_safely(tmp_path, monkeypatch):
    cfg = tmp_path / "config.system.json"
    cfg.write_text(
        json.dumps({"manga_video": {"audio_source": "unknown", "audio_fade_ms": 0}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", cfg)

    assert defaults.default_manga_video_audio_source() == "faded"
    assert defaults.default_manga_video_audio_fade_ms() == 8.0
