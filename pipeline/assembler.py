import os
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


def _get_clip_duration(path: str) -> float:
    return _get_duration(path)


def _build_concat_list(clips: List[str], clip_durations: dict, total_duration: float) -> List[str]:
    if not clips:
        raise AssembleError("No clips provided to concat list builder.")
    lines = []
    accumulated = 0.0
    i = 0
    while accumulated < total_duration:
        clip = clips[i % len(clips)]
        lines.append(f"file '{clip}'")
        accumulated += clip_durations[clip]
        i += 1
    return lines


def _build_encode_cmd(muxed: str, srt_path: Optional[str], output: str) -> List[str]:
    if srt_path:
        # Escape path for ffmpeg subtitles filter (forward slashes, escape colons on Windows)
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        vf = (
            f"subtitles={srt_escaped}:force_style="
            "'FontName=Arial,FontSize=18,Bold=1,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
            "Outline=2,MarginV=120,Alignment=2'"
        )
        return [
            "ffmpeg", "-y", "-i", muxed,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "copy", "-movflags", "+faststart",
            output,
        ]
    else:
        return [
            "ffmpeg", "-y", "-i", muxed,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "copy", "-movflags", "+faststart",
            output,
        ]


def assemble(
    raw_clips: List[str],
    audio_path: str,
    srt_path: Optional[str],
    output_path: str,
    work_dir: Optional[str] = None,
) -> None:
    """
    Assemble final video from stock clips, voice audio, and optional subtitles.

    Pipeline:
      1. Scale/crop each clip to 1080x1920
      2. Get audio duration
      3. Build looped concat to match audio duration
      4. Mux audio
      5. Encode with optional subtitle burn

    Args:
        raw_clips: List of downloaded stock clip paths.
        audio_path: Path to ElevenLabs .mp3.
        srt_path: Path to .srt file, or None.
        output_path: Where to write final.mp4.
        work_dir: Directory for intermediate files (defaults to output dir).

    Raises:
        AssembleError: If any ffmpeg step fails.
    """
    out = Path(output_path)
    work = Path(work_dir) if work_dir else out.parent
    work.mkdir(parents=True, exist_ok=True)

    intermediates = []

    try:
        # Step 1: Scale each clip to 1080x1920
        scaled_clips = []
        for i, clip in enumerate(raw_clips):
            scaled = str(work / f"clip_{i}_scaled.mp4")
            _run([
                "ffmpeg", "-y", "-i", clip,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                "-an", scaled,
            ])
            scaled_clips.append(scaled)
            intermediates.append(scaled)

        # Step 2: Get audio duration
        audio_duration = _get_duration(audio_path)

        # Step 3: Build concat list with looping
        clip_durations = {c: _get_clip_duration(c) for c in scaled_clips}
        concat_lines = _build_concat_list(scaled_clips, clip_durations, audio_duration)
        concat_file = work / "concat.txt"
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
        intermediates.append(str(concat_file))

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

        # Step 5: Encode with or without subtitles
        cmd = _build_encode_cmd(muxed, srt_path, str(out))
        _run(cmd)

    finally:
        # Clean up intermediates (only if final.mp4 was created)
        if out.exists():
            for f in intermediates:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
