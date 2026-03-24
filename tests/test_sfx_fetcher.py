import pytest
from pathlib import Path
from unittest.mock import patch

from pipeline.sfx_fetcher import get_sfx_cues


WORD_TIMINGS = [
    {"word": "Jasper", "start": 0.1, "end": 0.4},
    {"word": "is", "start": 0.4, "end": 0.5},
    {"word": "free", "start": 0.5, "end": 0.8},
    {"word": "$47", "start": 0.9, "end": 1.2},
    {"word": "now", "start": 1.3, "end": 1.5},
]
KEY_WORDS = ["free", "$47", "Jasper", "now"]


def make_sfx_dir(tmp_path: Path) -> Path:
    sfx_dir = tmp_path / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "whoosh.mp3").write_bytes(b"fake")
    (sfx_dir / "impact.mp3").write_bytes(b"fake")
    (sfx_dir / "ding.mp3").write_bytes(b"fake")
    return sfx_dir


def test_transition_cues_fire_at_intervals(tmp_path):
    sfx_dir = make_sfx_dir(tmp_path)
    with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
        cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=7.5)
    transition_cues = [c for c in cues if c[1].endswith("whoosh.mp3")]
    timestamps = [c[0] for c in transition_cues]
    assert 0 in timestamps
    assert 2500 in timestamps
    assert 5000 in timestamps


def test_impact_cue_on_digit_keyword(tmp_path):
    sfx_dir = make_sfx_dir(tmp_path)
    with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
        cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
    impact_cues = [c for c in cues if c[1].endswith("impact.mp3")]
    assert len(impact_cues) == 1
    assert impact_cues[0][0] == 900  # $47 starts at 0.9s = 900ms


def test_ding_cue_on_ding_keyword(tmp_path):
    sfx_dir = make_sfx_dir(tmp_path)
    with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
        cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
    ding_cues = [c for c in cues if c[1].endswith("ding.mp3")]
    ding_timestamps = [c[0] for c in ding_cues]
    assert 500 in ding_timestamps   # "free" at 0.5s
    assert 1300 in ding_timestamps  # "now" at 1.3s


def test_missing_sfx_file_skips_silently(tmp_path):
    sfx_dir = make_sfx_dir(tmp_path)
    (sfx_dir / "impact.mp3").unlink()  # remove impact
    with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
        cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
    assert not any(c[1].endswith("impact.mp3") for c in cues)


def test_output_sorted_by_timestamp(tmp_path):
    sfx_dir = make_sfx_dir(tmp_path)
    with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
        cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
    timestamps = [c[0] for c in cues]
    assert timestamps == sorted(timestamps)
