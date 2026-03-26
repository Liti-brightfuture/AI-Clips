import math
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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


@dataclass
class SlotClip:
    source: str          # file path
    offset: float        # start offset in source file (seconds)
    duration: float      # how long to use (seconds)
    is_user_asset: bool
    is_image: bool       # True if PNG/JPG → needs Ken Burns conversion


def build_slot_timeline(
    shot_list: list,
    asset_records: list,
    pexels_clips: list,
) -> List["SlotClip"]:
    """
    Build a flat list of 2.5s slots for the whole video.

    NOTE: shot_list is a list of plain dicts (from JSON), NOT ShotScene objects.
    The caller (_run_produce_pipeline_sync) passes shot_list_json directly — no
    deserialization to ShotScene needed. Dict keys: "scene" (int), "duration" (str).

    shot_list: list of dicts with "scene" (int) and "duration" (str like "5s")
    asset_records: list of AssetRecord objects with scene_hint and file_path
    pexels_clips: list of str file paths
    """
    SLOT_DURATION = 2.5

    # Build scene_number → asset path map (first asset per scene wins)
    asset_map: Dict[int, str] = {}
    for rec in asset_records:
        if rec.scene_hint is not None and rec.scene_hint not in asset_map:
            asset_map[rec.scene_hint] = rec.file_path
    # Assets with no scene_hint go into a fallback pool
    unassigned_assets = [rec.file_path for rec in asset_records if rec.scene_hint is None]

    # Pexels pool — shuffle once
    pool = list(pexels_clips)
    random.shuffle(pool)
    pool_iter = iter(pool)

    def next_pexels() -> str:
        nonlocal pool, pool_iter
        clip = next(pool_iter, None)
        if clip is None:
            pool = list(pexels_clips)
            random.shuffle(pool)
            pool_iter = iter(pool)
            clip = next(pool_iter)
        return clip

    slots = []
    for scene_data in shot_list:
        scene_num = scene_data["scene"]
        raw_dur = scene_data.get("duration", "3s")
        scene_dur = int("".join(c for c in raw_dur if c.isdigit()) or "3")
        n_slots = math.ceil(scene_dur / SLOT_DURATION)
        asset_path = asset_map.get(scene_num)

        for i in range(n_slots):
            slot_dur = min(SLOT_DURATION, scene_dur - i * SLOT_DURATION)
            if slot_dur <= 0:
                break
            if asset_path:
                is_img = asset_path.lower().endswith((".png", ".jpg", ".jpeg"))
                slots.append(SlotClip(
                    source=asset_path,
                    offset=i * SLOT_DURATION,
                    duration=slot_dur,
                    is_user_asset=True,
                    is_image=is_img,
                ))
            else:
                pexels = next_pexels()
                slots.append(SlotClip(
                    source=pexels,
                    offset=0.0,
                    duration=slot_dur,
                    is_user_asset=False,
                    is_image=False,
                ))

    return slots


def _screenshot_to_clip(image_path: str, duration: float, output_path: str) -> None:
    """Convert a PNG/JPG to a Ken Burns video (100%→105% zoom-in)."""
    n_frames = max(1, int(duration * 30))
    zoom_step = round(0.05 / n_frames, 6)
    vf = (
        f"zoompan=z='min(zoom+{zoom_step},1.05)':d={n_frames}:s=1080x1920:fps=30,"
        "format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
        output_path,
    ])


def _recording_to_clip(video_path: str, duration: float, output_path: str) -> None:
    """Trim or pad a screen recording to exact duration."""
    src_dur = _get_duration(video_path)
    if src_dur >= duration:
        # Trim
        _run(["ffmpeg", "-y", "-i", video_path, "-t", str(duration), "-c", "copy", output_path])
    else:
        # Pad by freezing last frame
        pad = duration - src_dur
        _run([
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad}",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", output_path,
        ])


def assemble_with_assets(
    slots: List[SlotClip],
    audio_path: str,
    ass_path: Optional[str],
    sfx_cues: List[tuple],
    output_path: str,
    work_dir: Optional[str] = None,
) -> None:
    """
    Assemble final video from a slot timeline (user assets + pexels fill).
    Follows the same 5-step pipeline as assemble() but uses pre-built slots.
    """
    out = Path(output_path)
    work = Path(work_dir) if work_dir else out.parent
    work.mkdir(parents=True, exist_ok=True)
    intermediates = []

    try:
        # Step 1: Convert each slot to a 1080x1920 clip of exact duration
        slot_clips = []
        for i, slot in enumerate(slots):
            slot_out = str(work / f"slot_{i}.mp4")
            if slot.is_image:
                _screenshot_to_clip(slot.source, slot.duration, slot_out)
            elif slot.is_user_asset:
                _recording_to_clip(slot.source, slot.duration, slot_out)
            else:
                # Pexels clip: scale + trim as in standard assemble()
                _run([
                    "ffmpeg", "-y", "-i", slot.source,
                    "-t", str(slot.duration),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                    "-an", slot_out,
                ])
            slot_clips.append(slot_out)
            intermediates.append(slot_out)

        # Step 2: Audio duration
        audio_duration = _get_duration(audio_path)

        # Step 3: Concat slots into single video_raw (may be shorter/longer than audio)
        concat_file = work / "concat_assets.txt"
        concat_lines = [f"file '{c}'" for c in slot_clips]
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

        # Steps 4, 4.5, 5: identical to assemble()
        muxed = str(work / "muxed.mp4")
        _run([
            "ffmpeg", "-y", "-i", video_raw, "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-shortest", muxed,
        ])
        intermediates.append(muxed)

        if sfx_cues:
            sfx_mixed = str(work / "audio_with_sfx.mp4")
            _mix_sfx(muxed, sfx_cues, sfx_mixed)
            encode_input = sfx_mixed
            intermediates.append(sfx_mixed)
        else:
            encode_input = muxed

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
