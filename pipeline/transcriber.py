import logging
import re
from pathlib import Path
from typing import Optional

from pipeline.exceptions import TranscribeError

logger = logging.getLogger(__name__)

ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,10,10,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _load_model():
    import whisper
    return whisper.load_model("base")


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02}:{s:05.2f}"


def _strip_punct(word: str) -> str:
    return re.sub(r"[^\w$]", "", word).lower()


def _words_to_ass(word_timings: list[dict], key_words: list[str]) -> str:
    kw_set = {_strip_punct(kw) for kw in key_words}
    lines = [ASS_HEADER.rstrip()]
    for entry in word_timings:
        start = _ass_time(entry["start"])
        end = _ass_time(entry["end"])
        word = entry["word"].strip()
        if not word:
            continue
        if _strip_punct(word) in kw_set:
            text = f"{{\\c&H0000FFFF&}}{word}{{\\r}}"
        else:
            text = word
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return "\n".join(lines)


def _extract_word_timings(segments: list) -> list[dict]:
    """Extract per-word timings from Whisper segments. Falls back to segment-level."""
    timings = []
    for seg in segments:
        words = seg.get("words") or []
        if words:
            for w in words:
                timings.append({
                    "word": w.get("word", ""),
                    "start": float(w.get("start", seg["start"])),
                    "end": float(w.get("end", seg["end"])),
                })
        else:
            # Fallback: treat entire segment text as one entry
            timings.append({
                "word": seg["text"].strip(),
                "start": float(seg["start"]),
                "end": float(seg["end"]),
            })
    return timings


def transcribe(audio_path: str, output_dir: str, key_words: Optional[list] = None) -> tuple[str, list[dict]]:
    """
    Transcribe audio with Whisper and write a .ass subtitle file.

    Args:
        audio_path: Path to the .mp3 file.
        output_dir: Directory to write subs.ass.
        key_words: Words to highlight yellow. Defaults to [].

    Returns:
        (ass_path, word_timings) — path to subs.ass and list of
        {"word": str, "start": float, "end": float} dicts.

    Raises:
        TranscribeError: On any failure. Caught by the queue worker (non-fatal).
    """
    if key_words is None:
        key_words = []
    try:
        model = _load_model()
        result = model.transcribe(audio_path, word_timestamps=True)
        segments = result.get("segments", [])
        word_timings = _extract_word_timings(segments)
        ass_content = _words_to_ass(word_timings, key_words)
        ass_path = Path(output_dir) / "subs.ass"
        ass_path.write_text(ass_content, encoding="utf-8")
        return str(ass_path), word_timings
    except Exception as e:
        raise TranscribeError(f"Whisper transcription failed: {e}") from e
