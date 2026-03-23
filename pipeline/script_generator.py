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
Return ONLY valid JSON, no markdown, no code fences:
{{"script": string, "pexels_keywords": [string, string, string], "hook_line": string, "tool_benefit": string}}"""

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
Return ONLY valid JSON, no markdown, no code fences:
{{"script": string, "pexels_keywords": [string, string, string], "hook_line": string, "data_point": string}}"""

REQUIRED_MONEY_FIELDS = {"script", "pexels_keywords", "hook_line", "tool_benefit"}
REQUIRED_B2B_FIELDS = {"script", "pexels_keywords", "hook_line", "data_point"}


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

    if command == "money":
        prompt = MONEY_SYSTEM_PROMPT.format(topic=topic)
        required_fields = REQUIRED_MONEY_FIELDS
    else:
        research = research_text or "No research data available."
        prompt = B2B_SYSTEM_PROMPT.format(topic=topic, research=research)
        required_fields = REQUIRED_B2B_FIELDS

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        raise ScriptError(f"GPT-4o returned invalid JSON: {e}") from e

    missing = required_fields - set(data.keys())
    if missing:
        raise ScriptError(f"GPT-4o response missing fields: {missing}")

    if not isinstance(data.get("pexels_keywords"), list) or len(data["pexels_keywords"]) != 3:
        raise ScriptError("pexels_keywords must be a list of 3 strings")

    return data
