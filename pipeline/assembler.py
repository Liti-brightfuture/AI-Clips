import os
import random
import subprocess
from pathlib import Path
from typing import List, Optional

from pipeline.exceptions import AssembleError


def _run(cmd: List[str], cwd: Optional[str] = None) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise AssembleError(f"ffmpeg failed:\n{result.stderr[-1000:]}")


def _get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise AssembleError(f"ffprobe failed on {path}")
    return float(result.stdout.strip())


def get_audio_duration(path: str) -> float:
    """Public wrapper — returns duration in seconds via ffprobe."""
    return _get_duration(path)


def _get_clip_duration(path: str) -> float:
    return _get_duration(path)


def _build_concat_list(clips: List[str], clip_durations: dict, total_duration: float) -> List[str]:
    if not clips:
        raise AssembleError("No clips provided to concat list builder.")
    shuffled = list(clips)
    random.shuffle(shuffled)
    lines = []
    accumulated = 0.0
    pool = list(shuffled)
    pool_iter = iter(pool)
    while accumulated < total_duration:
        clip = next(pool_iter, None)
        if clip is None:
            # Pool exhausted — re-shuffle and restart
            pool = list(shuffled)
            random.shuffle(pool)
            pool_iter = iter(pool)
            clip = next(pool_iter)
        lines.append(f"file '{clip}'")
        accumulated += clip_durations[clip]
    return lines


def _build_encode_cmd(input_path: str, ass_name: Optional[str], output: str) -> List[str]:
    """
    input_path: muxed.mp4 or audio_with_sfx.mp4
    ass_name: basename only (e.g. "subs.ass") — cwd workaround for Windows paths
    """
    if ass_name:
        vf = (
            f"subtitles={ass_name}:force_style="
            "'FontName=Arial,FontSize=65,Bold=1,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
            "Outline=3,MarginV=480,Alignment=2'"
        )
        return [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "copy", "-movflags", "+faststart",
            output,
        ]
    else:
        return [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "copy", "-movflags", "+faststart",
            output,
        ]


def _mix_sfx(muxed: str, sfx_cues: List[tuple], output: str) -> None:
    """Mix SFX into muxed video at specified timestamps. Output is a new .mp4."""
    cmd = ["ffmpeg", "-y", "-i", muxed]
    filter_parts = []
    for i, (ts_ms, sfx_path) in enumerate(sfx_cues):
        cmd += ["-i", sfx_path]
        idx = i + 1
        filter_parts.append(
            f"[{idx}:a]adelay={ts_ms}|{ts_ms},volume=-12dB[s{idx}]"
        )
    n = len(sfx_cues)
    inputs = "[0:a]" + "".join(f"[s{i+1}]" for i in range(n))
    filter_parts.append(f"{inputs}amix=inputs={n + 1}:normalize=0[aout]")
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac",
        output,
    ]
    _run(cmd)


def assemble(
    raw_clips: List[str],
    audio_path: str,
    ass_path: Optional[str],
    sfx_cues: List[tuple],
    output_path: str,
    work_dir: Optional[str] = None,
) -> None:
    """
    Assemble final video from stock clips, voice audio, optional captions and SFX.

    Args:
        raw_clips: Downloaded stock clip paths.
        audio_path: Path to .mp3 voice file.
        ass_path: Path to .ass subtitle file, or None.
        sfx_cues: List of (timestamp_ms, sfx_path). Pass [] for no SFX.
        output_path: Where to write final.mp4.
        work_dir: Directory for intermediates (defaults to output dir).

    Raises:
        AssembleError: If any ffmpeg step fails.
    """
    out = Path(output_path)
    work = Path(work_dir) if work_dir else out.parent
    work.mkdir(parents=True, exist_ok=True)

    intermediates = []

    try:
        # Step 1: Scale/crop each clip to 1080x1920, max 2.5 seconds
        scaled_clips = []
        for i, clip in enumerate(raw_clips):
            scaled = str(work / f"clip_{i}_scaled.mp4")
            _run([
                "ffmpeg", "-y", "-i", clip,
                "-t", "2.5",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                "-an", scaled,
            ])
            scaled_clips.append(scaled)
            intermediates.append(scaled)

        # Step 2: Get audio duration
        audio_duration = _get_duration(audio_path)

        # Step 3: Build concat list
        clip_durations = {c: _get_clip_duration(c) for c in scaled_clips}
        concat_lines = _build_concat_list(scaled_clips, clip_durations, audio_duration)
        concat_file = work / "concat.txt"
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
        intermediates.append(str(concat_file))

        # Step 3.5: Concat clips
        video_raw = str(work / "video_raw.mp4")
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-t", str(audio_duration),
            "-c", "copy", video_raw,
        ])
        intermediates.append(video_raw)

        # Step 4: Mux audio
        muxed = str(work / "muxed.mp4")
        _run([
            "ffmpeg", "-y", "-i", video_raw, "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-shortest", muxed,
        ])
        intermediates.append(muxed)

        # Step 4.5: Mix SFX (only if cues provided)
        if sfx_cues:
            sfx_mixed = str(work / "audio_with_sfx.mp4")
            _mix_sfx(muxed, sfx_cues, sfx_mixed)
            encode_input = sfx_mixed
            intermediates.append(sfx_mixed)
        else:
            encode_input = muxed

        # Step 5: Encode with optional ASS captions
        ass_name = Path(ass_path).name if ass_path else None
        cmd = _build_encode_cmd(encode_input, ass_name, str(out))
        _run(cmd, cwd=str(work))

    finally:
        if out.exists():
            for f in intermediates:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
