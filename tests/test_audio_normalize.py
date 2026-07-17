from argparse import Namespace

import pytest

from mediaconductor.video_pipeline.normalize_long_audio import (
    DEFAULT_CODEC_PEAK_MARGIN_DB,
    filter_target_tp,
    loudnorm_base,
)


def _args(**overrides):
    values = {
        "target_i": -14.0,
        "target_tp": -1.5,
        "target_lra": 11.0,
        "codec_peak_margin": DEFAULT_CODEC_PEAK_MARGIN_DB,
    }
    values.update(overrides)
    return Namespace(**values)


def test_aac_peak_margin_tightens_filter_target():
    args = _args()
    assert filter_target_tp(args) == pytest.approx(-2.3)
    assert "TP=-2.3" in loudnorm_base(args)


def test_zero_peak_margin_preserves_requested_target():
    args = _args(codec_peak_margin=0.0)
    assert filter_target_tp(args) == -1.5
    assert "TP=-1.5" in loudnorm_base(args)
