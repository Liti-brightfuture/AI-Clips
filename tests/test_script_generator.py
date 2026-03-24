# tests/test_script_generator.py
import json
import pytest
from unittest.mock import MagicMock, patch


MOCK_MONEY_RESPONSE = {
    "script": "AI is changing everything. Most people waste 4 hours writing. Jasper writes it in 4 minutes. Try it free. Link in bio — free trial, no card needed.",
    "pexels_keywords": ["artificial intelligence", "laptop typing", "productivity"],
    "hook_line": "AI is changing everything.",
    "tool_benefit": "Jasper cuts your writing time from hours to minutes.",
    "key_words": ["free", "4 hours", "4 minutes", "Jasper", "trial"],
}

MOCK_B2B_RESPONSE = {
    "script": "HubSpot costs $800/month. Monday.com costs $200. Same features. Here is the breakdown. Full breakdown — link in bio.",
    "pexels_keywords": ["business meeting", "CRM software", "startup office"],
    "hook_line": "HubSpot costs $800/month.",
    "data_point": "Monday.com costs 75% less than HubSpot for teams under 50.",
    "key_words": ["$800", "$200", "75%", "HubSpot", "Monday.com"],
}


def make_mock_openai(response_dict: dict):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(response_dict)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_generate_money_script():
    from pipeline.script_generator import generate_script
    mock_client = make_mock_openai(MOCK_MONEY_RESPONSE)
    result = generate_script("Jasper AI review 2026", command="money", client=mock_client)
    assert result["script"] == MOCK_MONEY_RESPONSE["script"]
    assert len(result["pexels_keywords"]) == 3
    assert "hook_line" in result
    assert "tool_benefit" in result


def test_generate_b2b_script():
    from pipeline.script_generator import generate_script
    mock_client = make_mock_openai(MOCK_B2B_RESPONSE)
    result = generate_script(
        "HubSpot vs Monday.com",
        command="b2b",
        research_text="HubSpot pricing: $800/month. Monday.com: $200/month.",
        client=mock_client,
    )
    assert "data_point" in result
    assert "tool_benefit" not in result


def test_invalid_json_raises_script_error():
    from pipeline.script_generator import generate_script
    from pipeline.exceptions import ScriptError
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "not json at all"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with pytest.raises(ScriptError):
        generate_script("test topic", command="money", client=mock_client)


def test_missing_field_raises_script_error():
    from pipeline.script_generator import generate_script
    from pipeline.exceptions import ScriptError
    incomplete = {"script": "hello", "pexels_keywords": ["a", "b", "c"]}  # missing hook_line
    mock_client = make_mock_openai(incomplete)
    with pytest.raises(ScriptError):
        generate_script("test topic", command="money", client=mock_client)


def test_missing_key_words_raises_script_error():
    from pipeline.script_generator import generate_script
    from pipeline.exceptions import ScriptError
    incomplete = {**MOCK_MONEY_RESPONSE}
    del incomplete["key_words"]
    mock_client = make_mock_openai(incomplete)
    with pytest.raises(ScriptError):
        generate_script("test topic", command="money", client=mock_client)


def test_key_words_too_few_raises_script_error():
    from pipeline.script_generator import generate_script
    from pipeline.exceptions import ScriptError
    bad = {**MOCK_MONEY_RESPONSE, "key_words": ["only_one"]}
    mock_client = make_mock_openai(bad)
    with pytest.raises(ScriptError, match="key_words"):
        generate_script("test topic", command="money", client=mock_client)


def test_generate_money_script_has_key_words():
    from pipeline.script_generator import generate_script
    mock_client = make_mock_openai(MOCK_MONEY_RESPONSE)
    result = generate_script("Jasper AI review 2026", command="money", client=mock_client)
    assert "key_words" in result
    assert 5 <= len(result["key_words"]) <= 8
