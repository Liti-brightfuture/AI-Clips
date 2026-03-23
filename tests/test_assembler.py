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

        assemble(raw_clips, str(audio), None, str(output), work_dir=str(tmp_path))

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

    srt = str(tmp_path / "subs.srt")
    output = str(tmp_path / "final.mp4")
    cmd = _build_encode_cmd(str(tmp_path / "muxed.mp4"), srt, output)
    cmd_str = " ".join(cmd)
    assert "subtitles" in cmd_str
    assert "libx264" in cmd_str


def test_concat_list_cycles_clips(tmp_path):
    from pipeline.assembler import _build_concat_list

    clips = ["clip_0.mp4", "clip_1.mp4"]
    clip_durations = {"clip_0.mp4": 10.0, "clip_1.mp4": 12.0}
    lines = _build_concat_list(clips, clip_durations, total_duration=35.0)
    # Should cycle: clip_0(10), clip_1(12), clip_0(10) = 32s, need 3 more → clip_1
    assert len(lines) >= 3
    assert all("file" in line for line in lines if line.strip())
