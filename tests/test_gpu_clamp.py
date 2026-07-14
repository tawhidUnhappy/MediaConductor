"""--gpu-workers is clamped in code, not just warned about in docs."""

from mangaeasy.video_pipeline.common import GPU_WORKERS_SAFE_MAX, clamp_gpu_workers


def test_safe_values_pass_through():
    assert clamp_gpu_workers(1) == 1
    assert clamp_gpu_workers(4) == 4


def test_zero_or_negative_becomes_one():
    assert clamp_gpu_workers(0) == 1
    assert clamp_gpu_workers(-3) == 1


def test_above_max_is_clamped(capsys, monkeypatch):
    monkeypatch.delenv("MANGAEASY_UNSAFE_GPU_WORKERS", raising=False)
    assert clamp_gpu_workers(8) == GPU_WORKERS_SAFE_MAX
    assert "clamped" in capsys.readouterr().err


def test_unsafe_override(monkeypatch):
    monkeypatch.setenv("MANGAEASY_UNSAFE_GPU_WORKERS", "1")
    assert clamp_gpu_workers(8) == 8
