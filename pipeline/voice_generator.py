from pathlib import Path
from typing import Optional

from pipeline.exceptions import VoiceError

TTS_MODEL = "tts-1-hd"


def generate_voice(
    script: str,
    output_path: str,
    client=None,
    voice_name: Optional[str] = None,
) -> None:
    """
    Convert script text to speech via OpenAI TTS and save as .mp3.

    Args:
        script: The video script text.
        output_path: Where to write the .mp3 file.
        client: OpenAI client (injectable for testing).
        voice_name: OpenAI TTS voice name (e.g. 'onyx', 'nova').

    Raises:
        VoiceError: If voice_name is missing or the API call fails.
    """
    if client is None:
        import config
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        if voice_name is None:
            voice_name = "onyx"

    if voice_name is None:
        raise VoiceError("voice_name must be provided when supplying a custom client.")

    try:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice_name,
            input=script,
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        response.stream_to_file(output_path)
    except Exception as e:
        raise VoiceError(f"OpenAI TTS API call failed: {e}") from e
