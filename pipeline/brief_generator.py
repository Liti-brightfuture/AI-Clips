import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

from pipeline.asset_manager import slugify
from pipeline.exceptions import ScriptError

logger = logging.getLogger(__name__)

DB_PATH_DEFAULT = __import__("queue_manager").DB_PATH


BRIEF_SYSTEM_PROMPT = """You are a viral short-form video scriptwriter specialising in AI tool reviews.
Write a 45-55 second TikTok script about {topic}.
Structure: Hook (0-3s) → Problem (3-10s) → Demo (10-35s) → Result (35-48s) → CTA (48-55s).
Rules: No 'hey guys'. Start with bold claim or question. Max 10 words per sentence.
CTA must be: 'Link in bio — free trial, no card needed'.
Extract the tool name from the topic (e.g. 'Jasper AI' from 'Jasper AI review 2026').
Return a shot list of 5-8 scenes the creator should film on their screen.
Each scene: type (screenshot or screen_recording), duration in seconds as 'Ns' (e.g. '3s'),
what to capture, where to focus/zoom, and what text must be visible.
Return 3 Pexels search keywords as fallback B-roll.
Return the first sentence as hook_line, one benefit sentence as tool_benefit.
Return 5-8 key words or phrases from the script for caption highlighting.
Target: freelancers and students 18-30. Tone: confident, fast, slightly irreverent. English only.
The script field must contain ONLY the spoken words — no labels, timestamps, or markers."""

BRIEF_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "brief_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "hook_line": {"type": "string"},
                "tool_benefit": {"type": "string"},
                "tool_name": {"type": "string"},
                "key_words": {"type": "array", "items": {"type": "string"}},
                "pexels_keywords": {"type": "array", "items": {"type": "string"}},
                "shot_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene": {"type": "integer"},
                            "duration": {"type": "string"},
                            "type": {"type": "string"},
                            "capture": {"type": "string"},
                            "focus": {"type": "string"},
                            "visible_text": {"type": "string"},
                        },
                        "required": ["scene", "duration", "type", "capture", "focus", "visible_text"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["script", "hook_line", "tool_benefit", "tool_name",
                         "key_words", "pexels_keywords", "shot_list"],
            "additionalProperties": False,
        },
    },
}

REQUIRED_BRIEF_FIELDS = {"script", "hook_line", "tool_benefit", "tool_name",
                          "key_words", "pexels_keywords", "shot_list"}


@dataclass
class ShotScene:
    scene: int
    duration: str       # e.g. "3s"
    type: str           # "screenshot" | "screen_recording"
    capture: str
    focus: str
    visible_text: str


@dataclass
class BriefResult:
    brief_id: int
    tool_slug: str
    tool_name: str
    topic: str
    script: str
    shot_list: List[ShotScene]
    voice: str
    pexels_keywords: List[str]
    chat_id: int


def _normalize_duration(raw: str) -> str:
    """Normalize '3s', '3 seconds', '3' → '3s'. Non-integer seconds → round up."""
    raw = raw.strip()
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return "3s"  # fallback
    return f"{int(digits)}s"


def generate_brief(
    topic: str,
    chat_id: int,
    db_path: str = DB_PATH_DEFAULT,
    client=None,
) -> "BriefResult":
    """
    Generate a production brief (script + shot list) using GPT-4o.
    Stores the brief in SQLite and returns a BriefResult.
    """
    if client is None:
        from openai import OpenAI
        import config
        client = OpenAI(api_key=config.OPENAI_API_KEY)

    prompt = BRIEF_SYSTEM_PROMPT.format(topic=topic)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format=BRIEF_SCHEMA,
        )
        raw = response.choices[0].message.content
    except Exception as e:
        raise ScriptError(f"GPT-4o brief generation failed: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScriptError(f"GPT-4o returned invalid JSON: {e}") from e

    missing = REQUIRED_BRIEF_FIELDS - set(data.keys())
    if missing:
        raise ScriptError(f"GPT-4o brief response missing fields: {missing}")

    shot_list_raw = data.get("shot_list", [])
    if not isinstance(shot_list_raw, list) or len(shot_list_raw) == 0:
        raise ScriptError("shot_list must be a non-empty array")

    shot_list = [
        ShotScene(
            scene=s["scene"],
            duration=_normalize_duration(s["duration"]),
            type=s["type"],
            capture=s["capture"],
            focus=s["focus"],
            visible_text=s["visible_text"],
        )
        for s in shot_list_raw
    ]

    tool_name = data["tool_name"]
    tool_slug = slugify(tool_name)

    # Resolve voice — only read config when running for real (client was None)
    try:
        import config
        voice = config.OPENAI_VOICE_MONEY
    except Exception:
        voice = "echo"

    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO briefs (tool_slug, tool_name, topic, script_json, shot_list_json, voice, chat_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            tool_slug,
            tool_name,
            topic,
            json.dumps(data),
            json.dumps(shot_list_raw),
            voice,
            chat_id,
        ),
    )
    brief_id = cur.lastrowid
    conn.commit()
    conn.close()

    return BriefResult(
        brief_id=brief_id,
        tool_slug=tool_slug,
        tool_name=tool_name,
        topic=topic,
        script=data["script"],
        shot_list=shot_list,
        voice=voice,
        pexels_keywords=data["pexels_keywords"],
        chat_id=chat_id,
    )


def format_brief_message(result: BriefResult) -> str:
    """Format a BriefResult into a Telegram-ready text message."""
    lines = [
        f"📋 Brief #BR{result.brief_id} — {result.topic}",
        f"Tool: {result.tool_name}",
        "",
    ]
    for s in result.shot_list:
        icon = "📸" if s.type == "screenshot" else "🎬"
        lines.append(f"Scene {s.scene} ({s.duration}) {icon} {s.type.upper()}")
        lines.append(f"→ {s.capture}")
        lines.append(f"→ Focus: {s.focus}")
        lines.append(f"→ Text: {s.visible_text}")
        lines.append("")
    lines.append(f"📤 Send files with caption BR{result.brief_id}")
    lines.append(f"(or just send — I'll auto-assign to this brief)")
    lines.append(f"▶️ When ready: /produce BR{result.brief_id}")
    return "\n".join(lines)
