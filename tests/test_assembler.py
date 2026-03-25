import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


def test_assemble_calls_ffmpeg(tmp_path):
    from pipeline.assembler import assemble

    raw_clips = [str(tmp_path / f"clip_{i}.mp4") for i in range(3)]
    for p in raw_clips:
        Path(p).write_bytes(b"fake")
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake")
    output = tmp_path / "final.mp4"

    with patch("pipeline.assembler._run") as mock_run, \
         patch("pipeline.assembler._get_duration", return_value=50.0), \
         patch("pipeline.assembler._get_clip_duration", return_value=15.0):
        mock_run.return_value = None
        # Create fake intermediate files so cleanup doesn't error
        (tmp_path / "video_raw.mp4").write_bytes(b"x")
        (tmp_path / "muxed.mp4").write_bytes(b"x")
        (tmp_path / "final.mp4").write_bytes(b"x")

        assemble(raw_clips, str(audio), None, [], str(output), work_dir=str(tmp_path))

    assert mock_run.called


def test_assemble_without_subs_skips_subtitle_filter(tmp_path):
    from pipeline.assembler import _build_encode_cmd

    output = str(tmp_path / "final.mp4")
    cmd = _build_encode_cmd(str(tmp_path / "muxed.mp4"), None, output)
    cmd_str = " ".join(cmd)
    assert "subtitles" not in cmd_str
    assert "libx264" in cmd_str


def test_assemble_with_subs_includes_subtitle_filter(tmp_path):
    from pipeline.assembler import _build_encode_cmd

    output = str(tmp_path / "final.mp4")
    cmd = _build_encode_cmd(str(tmp_path / "muxed.mp4"), "subs.ass", output)
    cmd_str = " ".join(cmd)
    assert "subtitles" in cmd_str
    assert "libx264" in cmd_str


def test_concat_list_cycles_clips(tmp_path):
    from pipeline.assembler import _build_concat_list

    clips = ["clip_0.mp4", "clip_1.mp4"]
    clip_durations = {"clip_0.mp4": 10.0, "clip_1.mp4": 12.0}
    lines = _build_concat_list(clips, clip_durations, total_duration=35.0)
    # Clips are shuffled but should still cycle until total_duration is filled
    assert len(lines) >= 3
    assert all("file" in line for line in lines if line.strip())


def test_build_concat_list_shuffles_clips():
    """Verify clips are shuffled before cycling — not in fixed input order."""
    from pipeline.assembler import _build_concat_list
    import random

    clips = [f"/clip_{i}.mp4" for i in range(10)]
    durations = {c: 2.5 for c in clips}
    total_duration = 30.0  # 12 slots, cycles through more than 10 clips

    # Run 20 times; at least one run must produce an order different from input
    orders_seen = set()
    for _ in range(20):
        random.seed(None)  # ensure true randomness
        result = _build_concat_list(clips, durations, total_duration)
        # Capture first-pass order (first 10 entries)
        orders_seen.add(tuple(result[:10]))

    # Should have seen more than one ordering (probability of always same: (1/10!)^20 ≈ 0)
    assert len(orders_seen) > 1, "Clips were never shuffled — always same order"
