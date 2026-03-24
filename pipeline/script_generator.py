import json
from typing import Optional
from openai import OpenAI
from pipeline.exceptions import ScriptError

MONEY_SYSTEM_PROMPT = """You are a viral short-form video scriptwriter for AI tools.
Write a 45-55 second TikTok script about {topic}.
Structure: Hook (0-3s) → Problem (3-10s) → Demo (10-35s) → Result (35-48s) → CTA (48-55s).
Rules: No 'hey guys'. Start with bold claim or question. Max 10 words per sentence.
CTA must be: 'Link in bio — free trial, no card needed'.
Also return 3 Pexels search keywords relevant to the topic (for stock footage).
Return the first sentence of the script as hook_line.
Return one sentence describing the tool's main benefit as tool_benefit.
Target: freelancers and students 18-30. Tone: confident, fast, slightly irreverent. English only.
The script field must contain ONLY the spoken words. Do NOT include any structural labels, timestamps, or markers like 'Hook', 'Problem', 'Demo', etc.
Return 5-8 words or short phrases from the script as key_words — these will be highlighted yellow on screen. Pick numbers, prices, the tool name, power words (free, instant, best), and the CTA trigger word."""

B2B_SYSTEM_PROMPT = """You are a B2B SaaS reviewer creating short-form video scripts.
Use this research data (may be truncated): {research}
Write a 50-60 second script about {topic}.
Include REAL numbers from the research (pricing, ratings, user counts).
Structure: Hook → Problem → Solution → Data point → CTA.
CTA must be: 'Full breakdown — link in bio'.
Also return 3 Pexels search keywords relevant to the topic (for stock footage).
Return the first sentence of the script as hook_line.
Return one real data point (stat, price, or rating) as data_point.
Target: business owners and managers 28-45. Tone: authoritative, data-driven, direct. English only.
The script field must contain ONLY the spoken words. Do NOT include any structural labels, timestamps, or markers like 'Hook', 'Problem', 'Solution', 'Data point', 'CTA', etc.
Return 5-8 words or short phrases from the script as key_words — highlighted yellow on screen. Pick stats, prices, product names, and decisive words."""

MONEY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "money_script",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "pexels_keywords": {"type": "array", "items": {"type": "string"}},
                "hook_line": {"type": "string"},
                "tool_benefit": {"type": "string"},
                "key_words": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["script", "pexels_keywords", "hook_line", "tool_benefit", "key_words"],
            "additionalProperties": False,
        },
    },
}

B2B_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "b2b_script",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "pexels_keywords": {"type": "array", "items": {"type": "string"}},
                "hook_line": {"type": "string"},
                "data_point": {"type": "string"},
                "key_words": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["script", "pexels_keywords", "hook_line", "data_point", "key_words"],
            "additionalProperties": False,
        },
    },
}

REQUIRED_MONEY_FIELDS = {"script", "pexels_keywords", "hook_line", "tool_benefit", "key_words"}
REQUIRED_B2B_FIELDS = {"script", "pexels_keywords", "hook_line", "data_point", "key_words"}


def generate_script(
    topic: str,
    command: str,
    research_text: Optional[str] = None,
    client: Optional[OpenAI] = None,
) -> dict:
    """
    Generate a video script using GPT-4o.

    Args:
        topic: The video topic.
        command: "money" or "b2b".
        research_text: GPT Researcher output (b2b only, optional).
        client: OpenAI client instance (injectable for testing).

    Returns:
        Parsed JSON dict with script, pexels_keywords, hook_line, and
        tool_benefit (money) or data_point (b2b).

    Raises:
        ScriptError: If GPT-4o returns invalid JSON or missing fields.
    """
    if client is None:
        import config  # lazy import — only needed in production
        client = OpenAI(api_key=config.OPENAI_API_KEY)

    if command not in ("money", "b2b"):
        raise ValueError(f"Unknown command: {command!r}. Expected 'money' or 'b2b'.")

    if command == "money":
        prompt = MONEY_SYSTEM_PROMPT.format(topic=topic)
        required_fields = REQUIRED_MONEY_FIELDS
        schema = MONEY_SCHEMA
    else:
        research = research_text or "No research data available."
        prompt = B2B_SYSTEM_PROMPT.format(topic=topic, research=research)
        required_fields = REQUIRED_B2B_FIELDS
        schema = B2B_SCHEMA

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
        )
        raw = response.choices[0].message.content
    except Exception as e:
        raise ScriptError(f"GPT-4o API call failed: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScriptError(f"GPT-4o returned invalid JSON: {e}") from e

    missing = required_fields - set(data.keys())
    if missing:
        raise ScriptError(f"GPT-4o response missing fields: {missing}")

    keywords = data.get("pexels_keywords")
    if (
        not isinstance(keywords, list)
        or len(keywords) != 3
        or not all(isinstance(k, str) and k for k in keywords)
    ):
        raise ScriptError("pexels_keywords must be a list of 3 non-empty strings")

    key_words = data.get("key_words")
    if (
        not isinstance(key_words, list)
        or not (5 <= len(key_words) <= 8)
        or not all(isinstance(k, str) and k for k in key_words)
    ):
        raise ScriptError("key_words must be a list of 5-8 non-empty strings")

    return data
