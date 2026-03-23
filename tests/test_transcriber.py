import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


MOCK_WHISPER_RESULT = {
    "segments": [
        {"start": 0.0, "end": 2.5, "text": " AI is changing everything."},
        {"start": 2.5, "end": 6.0, "text": " Most people waste hours writing."},
    ]
}


def test_transcribe_returns_srt_path(tmp_path):
    from pipeline.transcriber import transcribe

    mock_model = MagicMock()
    mock_model.transcribe.return_value = MOCK_WHISPER_RESULT

    with patch("pipeline.transcriber._load_model", return_value=mock_model):
        srt_path = transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))

    assert srt_path is not None
    assert Path(srt_path).exists()
    content = Path(srt_path).read_text()
    assert "AI is changing everything." in content
    assert "-->" in content


def test_srt_format_is_valid(tmp_path):
    from pipeline.transcriber import transcribe

    mock_model = MagicMock()
    mock_model.transcribe.return_value = MOCK_WHISPER_RESULT

    with patch("pipeline.transcriber._load_model", return_value=mock_model):
        srt_path = transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))

    lines = Path(srt_path).read_text().strip().split("\n")
    assert lines[0] == "1"              # index
    assert "-->" in lines[1]            # timestamp line
    assert "00:00:00,000" in lines[1]   # start time


def test_raises_transcribe_error_on_failure(tmp_path):
    from pipeline.transcriber import transcribe
    from pipeline.exceptions import TranscribeError

    with patch("pipeline.transcriber._load_model", side_effect=RuntimeError("no model")):
        with pytest.raises(TranscribeError, match="Whisper transcription failed"):
            transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))
