import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

SFX_DIR = Path(__file__).parent.parent / "assets" / "sfx"

DING_WORDS = {"free", "now", "link", "click", "try"}
TRANSITION_INTERVAL_MS = 2500


def _strip_punct(word: str) -> str:
    return re.sub(r"[^\w$]", "", word).lower()


def get_sfx_cues(
    word_timings: list[dict],
    key_words: list[str],
    audio_duration: float,
) -> list[tuple[int, str]]:
    """
    Returns list of (timestamp_ms, sfx_path) sorted by timestamp.
    Only includes cues for SFX files that exist in assets/sfx/.
    Transition cues fire at 0, 2500, 5000, ... ms up to audio_duration*1000.
    """
    cues = []
    whoosh = SFX_DIR / "whoosh.mp3"
    impact = SFX_DIR / "impact.mp3"
    ding = SFX_DIR / "ding.mp3"

    # Transition cues every TRANSITION_INTERVAL_MS
    if whoosh.exists():
        t = 0
        limit = int(audio_duration * 1000)
        while t < limit:
            cues.append((t, str(whoosh)))
            t += TRANSITION_INTERVAL_MS
    else:
        logger.warning("SFX whoosh.mp3 not found in assets/sfx/ — skipping transitions")

    # Build word → start_ms lookup (first occurrence wins)
    word_map: dict[str, int] = {}
    for entry in word_timings:
        clean = _strip_punct(entry["word"])
        if clean and clean not in word_map:
            word_map[clean] = int(entry["start"] * 1000)

    # Impact cues — key words with digits or $
    if impact.exists():
        for kw in key_words:
            kw_clean = _strip_punct(kw)
            if any(c.isdigit() or c == "$" for c in kw_clean):
                if kw_clean in word_map:
                    cues.append((word_map[kw_clean], str(impact)))
    else:
        logger.warning("SFX impact.mp3 not found in assets/sfx/ — skipping impact cues")

    # Ding cues — key words in DING_WORDS set
    if ding.exists():
        for kw in key_words:
            kw_clean = _strip_punct(kw)
            if kw_clean in DING_WORDS and kw_clean in word_map:
                cues.append((word_map[kw_clean], str(ding)))
    else:
        logger.warning("SFX ding.mp3 not found in assets/sfx/ — skipping ding cues")

    return sorted(cues, key=lambda x: x[0])
