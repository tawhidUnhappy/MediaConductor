import numpy as np

from mediaconductor.video_pipeline.preprocess_audio_fades import (
    compute_adaptive_fade_out_ms,
    fade_filter,
)


def _tone(sr: int, ms: float, amplitude: float = 0.5, freq: float = 220.0) -> np.ndarray:
    n = int(sr * ms / 1000)
    t = np.arange(n) / sr
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(sr: int, ms: float) -> np.ndarray:
    return np.zeros(int(sr * ms / 1000), dtype=np.float32)


def test_ordinary_clip_keeps_floor_fade():
    sr = 22050
    # Speech tapering smoothly to silence well before the end -- no artifact.
    speech = _tone(sr, 300)
    tail_silence = _silence(sr, 100)
    samples = np.concatenate([speech, tail_silence])
    assert compute_adaptive_fade_out_ms(samples, sr, floor_ms=8.0) == 8.0


def test_clip_that_ends_loud_with_no_gap_keeps_floor_fade():
    sr = 22050
    # Continuous speech running straight to the end -- not an isolated artifact.
    samples = _tone(sr, 300)
    assert compute_adaptive_fade_out_ms(samples, sr, floor_ms=8.0) == 8.0


def test_trailing_click_after_silence_extends_fade_out():
    sr = 22050
    speech = _tone(sr, 300)
    quiet_gap = _silence(sr, 30)  # a real gap after speech has ended
    click_burst = _tone(sr, 20, amplitude=0.6, freq=1200.0)  # spurious tail burst
    samples = np.concatenate([speech, quiet_gap, click_burst])
    fade_out = compute_adaptive_fade_out_ms(samples, sr, floor_ms=8.0)
    assert fade_out > 8.0
    # The extended fade must reach back far enough to cover the whole burst,
    # i.e. past the 20 ms burst plus a little of the gap before it.
    assert fade_out >= 20.0


def test_silent_clip_keeps_floor_fade():
    sr = 22050
    samples = _silence(sr, 200)
    assert compute_adaptive_fade_out_ms(samples, sr, floor_ms=8.0) == 8.0


def test_fade_filter_uses_separate_in_and_out_durations():
    filt = fade_filter(duration=2.0, fade_in_seconds=0.008, fade_out_seconds=0.05)
    assert "afade=t=in:st=0:d=0.008000" in filt
    assert "afade=t=out:st=1.950000:d=0.050000" in filt


def test_fade_filter_clamps_to_a_quarter_of_duration():
    # A short clip shouldn't let either fade eat more than a quarter of it.
    filt = fade_filter(duration=0.02, fade_in_seconds=0.008, fade_out_seconds=0.15)
    assert "d=0.005000" in filt  # fade-out clamped to duration / 4
