import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


def make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "jobs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE usage (
            month TEXT PRIMARY KEY,
            chars_used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def test_generate_voice_writes_file(tmp_path):
    from pipeline.voice_generator import generate_voice
    db_path = make_db(tmp_path)
    output_path = tmp_path / "voice.mp3"

    mock_client = MagicMock()
    mock_client.text_to_speech.convert.return_value = [b"fake_audio_data"]

    generate_voice("Hello world", str(output_path), str(db_path), client=mock_client)
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake_audio_data"


def test_chars_tracked_in_db(tmp_path):
    from pipeline.voice_generator import generate_voice
    db_path = make_db(tmp_path)
    output_path = tmp_path / "voice.mp3"
    mock_client = MagicMock()
    mock_client.text_to_speech.convert.return_value = [b"data"]

    script = "Hello world"
    generate_voice(script, str(output_path), str(db_path), client=mock_client)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT chars_used FROM usage").fetchone()
    conn.close()
    assert row[0] == len(script.encode("utf-8"))


def test_hard_limit_raises_voice_error(tmp_path):
    from pipeline.voice_generator import generate_voice
    from pipeline.exceptions import VoiceError
    db_path = make_db(tmp_path)
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO usage VALUES (?, ?)", (month, 9999))
    conn.commit()
    conn.close()

    mock_client = MagicMock()
    with pytest.raises(VoiceError, match="monthly limit"):
        generate_voice("Hello world this is a long script", str(tmp_path / "v.mp3"), str(db_path), client=mock_client)


def test_warning_threshold_does_not_block(tmp_path):
    from pipeline.voice_generator import generate_voice
    db_path = make_db(tmp_path)
    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO usage VALUES (?, ?)", (month, 8990))  # 8990 + 13 bytes = 9003 > 9000 threshold
    conn.commit()
    conn.close()

    mock_client = MagicMock()
    mock_client.text_to_speech.convert.return_value = [b"data"]
    # Should not raise, but should return warning message
    warning = generate_voice("Short script.", str(tmp_path / "v.mp3"), str(db_path), client=mock_client)
    assert warning is not None  # warning message returned
