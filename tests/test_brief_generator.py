import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def make_db(tmp_path):
    db = str(tmp_path / "test.db")
    from queue_manager import init_db
    init_db(db)
    return db


def make_mock_gpt_response(tool_name="Jasper AI"):
    return json.dumps({
        "script": "Jasper AI writes your copy in seconds. No blank page. Ever.",
        "hook_line": "Jasper AI writes your copy in seconds.",
        "tool_benefit": "Generates marketing copy 10x faster than typing manually.",
        "tool_name": tool_name,
        "key_words": ["Jasper AI", "seconds", "copy", "free", "faster"],
        "pexels_keywords": ["AI writing", "laptop", "marketing"],
        "shot_list": [
            {
                "scene": 1,
                "duration": "3s",
                "type": "screenshot",
                "capture": "jasper.ai homepage full screen",
                "focus": "Top area, Start for free button",
                "visible_text": "URL jasper.ai and headline"
            },
            {
                "scene": 2,
                "duration": "5s",
                "type": "screen_recording",
                "capture": "Click New Document, type prompt, see AI generate",
                "focus": "Cursor visible, editor panel",
                "visible_text": "Prompt and AI output legible"
            }
        ]
    })


def test_generate_brief_returns_brief_result(tmp_path):
    from pipeline.brief_generator import generate_brief, BriefResult

    db = make_db(tmp_path)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=make_mock_gpt_response()))]
    )

    result = generate_brief("Jasper AI review", chat_id=12345, db_path=db, client=mock_client)

    assert isinstance(result, BriefResult)
    assert result.tool_name == "Jasper AI"
    assert result.tool_slug == "jasper_ai"
    assert len(result.shot_list) == 2
    assert result.chat_id == 12345
    assert result.voice == "echo"


def test_generate_brief_stores_in_db(tmp_path):
    from pipeline.brief_generator import generate_brief
    db = make_db(tmp_path)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=make_mock_gpt_response()))]
    )

    result = generate_brief("Jasper AI review", chat_id=12345, db_path=db, client=mock_client)

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT * FROM briefs WHERE id=?", (result.brief_id,)).fetchone()
    conn.close()
    assert row is not None
    assert row[2] == "jasper_ai"  # tool_slug column


def test_format_brief_message_contains_scene_info():
    from pipeline.brief_generator import format_brief_message, BriefResult, ShotScene

    result = BriefResult(
        brief_id=42,
        tool_slug="jasper_ai",
        tool_name="Jasper AI",
        topic="Jasper AI review",
        script="...",
        shot_list=[
            ShotScene(scene=1, duration="3s", type="screenshot",
                      capture="homepage", focus="top area", visible_text="URL"),
        ],
        voice="echo",
        pexels_keywords=["AI", "laptop", "marketing"],
        chat_id=12345,
    )
    msg = format_brief_message(result)
    assert "BR42" in msg
    assert "Scene 1" in msg
    assert "screenshot" in msg.lower() or "📸" in msg
    assert "/produce BR42" in msg


def test_generate_brief_raises_on_missing_fields(tmp_path):
    from pipeline.brief_generator import generate_brief
    from pipeline.exceptions import ScriptError
    db = make_db(tmp_path)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"script": "hi"}'))]
    )
    with pytest.raises(ScriptError):
        generate_brief("Jasper AI review", chat_id=12345, db_path=db, client=mock_client)
