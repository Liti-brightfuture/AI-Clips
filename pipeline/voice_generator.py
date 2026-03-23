import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline.exceptions import VoiceError

ELEVENLABS_HARD_LIMIT = 10_000
ELEVENLABS_WARN_THRESHOLD = 9_000


def _get_and_init_usage(conn: sqlite3.Connection) -> tuple[int, str]:
    month = datetime.now().strftime("%Y-%m")
    conn.execute(
        "INSERT OR IGNORE INTO usage (month, chars_used) VALUES (?, 0)",
        (month,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT chars_used FROM usage WHERE month = ?", (month,)
    ).fetchone()
    return row[0], month


def generate_voice(
    script: str,
    output_path: str,
    db_path: str,
    client=None,
    voice_id: Optional[str] = None,
) -> Optional[str]:
    """
    Convert script text to speech via ElevenLabs and save as .mp3.

    Args:
        script: The video script text.
        output_path: Where to write the .mp3 file.
        db_path: Path to jobs.db for char usage tracking.
        client: ElevenLabs client (injectable for testing).
        voice_id: ElevenLabs voice ID (injectable for testing).

    Returns:
        Warning message string if approaching limit, else None.

    Raises:
        VoiceError: If monthly char limit is exceeded or API call fails.
    """
    if client is None:
        import config
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        voice_id = config.ELEVENLABS_VOICE_ID

    if voice_id is None:
        raise VoiceError("voice_id must be provided when supplying a custom client.")

    script_len = len(script.encode("utf-8"))

    conn = sqlite3.connect(db_path)
    try:
        current, month = _get_and_init_usage(conn)

        # Count chars pre-call for limit checks, but only record usage after a successful API call.
        # This avoids charging the budget for failed requests.
        if current + script_len > ELEVENLABS_HARD_LIMIT:
            raise VoiceError(
                f"ElevenLabs monthly limit reached ({current}/{ELEVENLABS_HARD_LIMIT} chars used). "
                f"Resets on the 1st of next month."
            )

        warning = None
        if current + script_len > ELEVENLABS_WARN_THRESHOLD:
            remaining = ELEVENLABS_HARD_LIMIT - current
            warning = f"⚠️ ElevenLabs approaching monthly limit (~{remaining} chars left this month)."

        try:
            audio_stream = client.text_to_speech.convert(
                voice_id=voice_id,
                text=script,
                model_id="eleven_monolingual_v1",
            )
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in audio_stream:
                    f.write(chunk)
        except Exception as e:
            raise VoiceError(f"ElevenLabs API call failed: {e}") from e

        conn.execute(
            "UPDATE usage SET chars_used = chars_used + ? WHERE month = ?",
            (script_len, month),
        )
        conn.commit()

        return warning
    finally:
        conn.close()
