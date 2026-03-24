import pytest
from pathlib import Path
from unittest.mock import MagicMock


def test_generate_voice_writes_file(tmp_path):
    from pipeline.voice_generator import generate_voice, TTS_MODEL

    output_path = tmp_path / "voice.mp3"
    output_path.write_bytes(b"")

    mock_response = MagicMock()
    mock_client = MagicMock()
    mock_client.audio.speech.create.return_value = mock_response

    generate_voice("Hello world", str(output_path), client=mock_client, voice_name="nova")

    mock_client.audio.speech.create.assert_called_once_with(
        model=TTS_MODEL,
        voice="nova",
        input="Hello world",
    )
    mock_response.stream_to_file.assert_called_once_with(str(output_path))


def test_generate_voice_missing_voice_name_raises():
    from pipeline.voice_generator import generate_voice
    from pipeline.exceptions import VoiceError

    mock_client = MagicMock()
    with pytest.raises(VoiceError, match="voice_name"):
        generate_voice("Hello", "/tmp/out.mp3", client=mock_client, voice_name=None)


def test_generate_voice_api_error_raises_voice_error(tmp_path):
    from pipeline.voice_generator import generate_voice
    from pipeline.exceptions import VoiceError

    mock_client = MagicMock()
    mock_client.audio.speech.create.side_effect = RuntimeError("API down")

    with pytest.raises(VoiceError, match="OpenAI TTS API call failed"):
        generate_voice("Hello", str(tmp_path / "v.mp3"), client=mock_client, voice_name="onyx")
