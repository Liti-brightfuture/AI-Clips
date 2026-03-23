import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _load_model():
    import whisper
    return whisper.load_model("base")


def _seconds_to_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _segments_to_srt(segments: list) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _seconds_to_srt_time(seg["start"])
        end = _seconds_to_srt_time(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def transcribe(audio_path: str, output_dir: str) -> str:
    """
    Transcribe audio with Whisper and write a .srt subtitle file.

    Args:
        audio_path: Path to the .mp3 file.
        output_dir: Directory to write subs.srt.

    Returns:
        Path to subs.srt.

    Raises:
        TranscribeError: On any failure. Caught by the queue worker (non-fatal).
    """
    from pipeline.exceptions import TranscribeError
    try:
        model = _load_model()
        result = model.transcribe(audio_path)
        segments = result.get("segments", [])
        srt_content = _segments_to_srt(segments)
        srt_path = Path(output_dir) / "subs.srt"
        srt_path.write_text(srt_content, encoding="utf-8")
        return str(srt_path)
    except TranscribeError:
        raise
    except Exception as e:
        raise TranscribeError(f"Whisper transcription failed: {e}") from e
