import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


MOCK_WHISPER_RESULT_WORDS = {
    "segments": [
        {
            "start": 0.0, "end": 2.5, "text": " AI is changing everything.",
            "words": [
                {"word": "AI", "start": 0.0, "end": 0.3},
                {"word": "is", "start": 0.3, "end": 0.5},
                {"word": "changing", "start": 0.5, "end": 0.9},
                {"word": "everything.", "start": 0.9, "end": 1.4},
            ],
        },
        {
            "start": 2.5, "end": 6.0, "text": " Most people waste hours writing.",
            "words": [
                {"word": "Most", "start": 2.5, "end": 2.8},
                {"word": "people", "start": 2.8, "end": 3.1},
                {"word": "waste", "start": 3.1, "end": 3.5},
                {"word": "hours", "start": 3.5, "end": 3.9},
                {"word": "writing.", "start": 3.9, "end": 4.4},
            ],
        },
    ]
}

MOCK_WHISPER_RESULT_NO_WORDS = {
    "segments": [
        {"start": 0.0, "end": 2.5, "text": " AI is changing everything."},
        {"start": 2.5, "end": 6.0, "text": " Most people waste hours writing."},
    ]
}


def test_transcribe_returns_ass_path(tmp_path):
    from pipeline.transcriber import transcribe

    mock_model = MagicMock()
    mock_model.transcribe.return_value = MOCK_WHISPER_RESULT_WORDS

    with patch("pipeline.transcriber._load_model", return_value=mock_model):
        ass_path, word_timings = transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))

    assert ass_path.endswith(".ass")
    assert Path(ass_path).exists()
    assert isinstance(word_timings, list)
    assert len(word_timings) > 0
    assert all("word" in w and "start" in w and "end" in w for w in word_timings)


def test_ass_format_is_valid(tmp_path):
    from pipeline.transcriber import transcribe

    mock_model = MagicMock()
    mock_model.transcribe.return_value = MOCK_WHISPER_RESULT_WORDS

    with patch("pipeline.transcriber._load_model", return_value=mock_model):
        ass_path, _ = transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))

    content = Path(ass_path).read_text()
    assert "[Script Info]" in content
    assert "Dialogue:" in content
    assert "AI" in content


def test_fallback_to_segment_level_when_no_words(tmp_path):
    from pipeline.transcriber import transcribe

    mock_model = MagicMock()
    mock_model.transcribe.return_value = MOCK_WHISPER_RESULT_NO_WORDS

    with patch("pipeline.transcriber._load_model", return_value=mock_model):
        ass_path, word_timings = transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))

    # Fallback: one entry per segment, same schema
    assert len(word_timings) == 2
    assert all("word" in w and "start" in w and "end" in w for w in word_timings)
    assert word_timings[0]["start"] == 0.0
    assert word_timings[1]["start"] == 2.5


def test_raises_transcribe_error_on_failure(tmp_path):
    from pipeline.transcriber import transcribe
    from pipeline.exceptions import TranscribeError

    with patch("pipeline.transcriber._load_model", side_effect=RuntimeError("no model")):
        with pytest.raises(TranscribeError, match="Whisper transcription failed"):
            transcribe(str(tmp_path / "voice.mp3"), str(tmp_path))
