import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

import json
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import config
from queue_manager import (
    init_db, add_job, get_next_pending_job, update_job_status,
    set_job_output, set_job_failed, get_status_counts, get_done_jobs, DB_PATH,
    add_brief_job, add_produce_job, get_brief, get_pending_brief_for_chat,
)
from pipeline.script_generator import generate_script
from pipeline.voice_generator import generate_voice
from pipeline.video_fetcher import fetch_clips
from pipeline.transcriber import transcribe
from pipeline.assembler import assemble, build_slot_timeline, assemble_with_assets
from pipeline.sfx_fetcher import get_sfx_cues
from pipeline.assembler import get_audio_duration
from pipeline.caption_generator import generate_caption
from pipeline.brief_generator import generate_brief, format_brief_message
from pipeline.asset_manager import store_asset, get_assets_for_tool, get_assets_for_brief, delete_asset, list_tools, slugify
from pipeline.exceptions import (
    ScriptError, VoiceError, VideoFetchError, TranscribeError, AssembleError, ResearchError
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Will be set after Application is built
_app: Application = None


def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == config.ALLOWED_CHAT_ID


def _run_money_pipeline_sync(topic: str, job_dir: Path) -> tuple:
    """Blocking pipeline — runs in executor thread."""
    script_data = generate_script(topic, command="money")
    script = script_data["script"]
    keywords = script_data["pexels_keywords"]

    voice_path = str(job_dir / "voice.mp3")
    warning = generate_voice(script, voice_path, voice_name=config.OPENAI_VOICE_MONEY)

    raw_clips = fetch_clips(keywords, str(job_dir), command="money")

    try:
        ass_path, word_timings = transcribe(voice_path, str(job_dir), script_data.get("key_words", []))
        audio_duration = get_audio_duration(voice_path)
        sfx_cues = get_sfx_cues(word_timings, script_data.get("key_words", []), audio_duration)
    except TranscribeError:
        ass_path = None
        sfx_cues = []

    final_path = job_dir / "final.mp4"
    assemble(raw_clips, voice_path, ass_path, sfx_cues, str(final_path))

    caption = generate_caption(script_data, command="money")
    return final_path, caption, warning


def _run_b2b_pipeline_sync(topic: str, job_dir: Path) -> tuple:
    """Blocking pipeline for /b2b — runs in executor thread."""
    from researcher import run_research

    research_text = run_research(topic, config.GPT_RESEARCHER_PATH)

    script_data = generate_script(topic, command="b2b", research_text=research_text)
    script = script_data["script"]
    keywords = script_data["pexels_keywords"]

    voice_path = str(job_dir / "voice.mp3")
    warning = generate_voice(script, voice_path, voice_name=config.OPENAI_VOICE_B2B)

    raw_clips = fetch_clips(keywords, str(job_dir), command="b2b")

    try:
        ass_path, word_timings = transcribe(voice_path, str(job_dir), script_data.get("key_words", []))
        audio_duration = get_audio_duration(voice_path)
        sfx_cues = get_sfx_cues(word_timings, script_data.get("key_words", []), audio_duration)
    except TranscribeError:
        ass_path = None
        sfx_cues = []

    final_path = job_dir / "final.mp4"
    assemble(raw_clips, voice_path, ass_path, sfx_cues, str(final_path))

    caption = generate_caption(script_data, command="b2b")
    return final_path, caption, warning


def _run_produce_pipeline_sync(brief: dict, job_dir: Path) -> tuple:
    """Blocking produce pipeline using brief assets + pexels fill."""
    script_json = json.loads(brief["script_json"])
    shot_list_json = json.loads(brief["shot_list_json"])
    topic = brief["topic"]
    tool_slug = brief["tool_slug"]
    voice = brief["voice"]

    script = script_json["script"]
    key_words = script_json.get("key_words", [])
    pexels_keywords = script_json.get("pexels_keywords", ["technology", "laptop", "work"])

    voice_path = str(job_dir / "voice.mp3")
    warning = generate_voice(script, voice_path, voice_name=voice)

    raw_clips = fetch_clips(pexels_keywords, str(job_dir), command="money")

    try:
        ass_path, word_timings = transcribe(voice_path, str(job_dir), key_words)
        audio_duration = get_audio_duration(voice_path)
        sfx_cues = get_sfx_cues(word_timings, key_words, audio_duration)
    except TranscribeError:
        ass_path = None
        sfx_cues = []

    # Use brief-scoped assets first; supplement with any tool-level assets (no brief_id)
    brief_assets = get_assets_for_brief(brief["id"])
    tool_assets_unscoped = [a for a in get_assets_for_tool(tool_slug) if a.brief_id is None]
    asset_records = brief_assets + tool_assets_unscoped
    slots = build_slot_timeline(shot_list_json, asset_records, raw_clips)

    final_path = job_dir / "final.mp4"
    assemble_with_assets(slots, voice_path, ass_path, sfx_cues, str(final_path))

    caption_data = {
        "hook_line": script_json.get("hook_line", topic),
        "tool_benefit": script_json.get("tool_benefit", ""),
        "pexels_keywords": pexels_keywords,
        "key_words": key_words,
    }
    caption = generate_caption(caption_data, command="money")
    return final_path, caption, warning


ACCOUNT_DIR = {"money": "account1", "b2b": "account2"}
PIPELINE_FN = {"money": _run_money_pipeline_sync, "b2b": _run_b2b_pipeline_sync}
FATAL_ERRORS = (ScriptError, VoiceError, VideoFetchError, AssembleError, ResearchError)

# User-facing error messages
ERROR_MESSAGES = {
    ScriptError: "Script generation failed. Check your OpenAI key or try again.",
    VoiceError: "Voice generation failed. ElevenLabs may be rate-limited or limit reached.",
    VideoFetchError: "Could not find stock footage. Try a different topic.",
    AssembleError: "Video assembly failed. Check ffmpeg is installed and in PATH.",
    ResearchError: "Research step timed out. Try a simpler topic.",
}


async def dispatch_brief_or_produce(job: dict) -> None:
    """Handle 'brief' and 'produce' job types — bypasses ACCOUNT_DIR."""
    job_id = job["job_id"]
    command = job["command"]
    topic = job["topic"]
    chat_id = job["chat_id"]
    loop = asyncio.get_event_loop()
    update_job_status(job_id, "running")

    try:
        if command == "brief":
            result = await loop.run_in_executor(
                None,
                lambda: generate_brief(topic, chat_id=chat_id),
            )
            msg = format_brief_message(result)
            set_job_output(job_id, f"brief:{result.brief_id}")
            if _app:
                await _app.bot.send_message(chat_id=chat_id, text=msg)

        elif command == "produce":
            brief_id = int(topic.split(":")[1])
            brief = get_brief(brief_id)
            if brief is None:
                raise AssembleError(f"Brief #{brief_id} not found.")

            job_dir = config.OUTPUT_DIR / "briefs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            final_path, caption, warning = await loop.run_in_executor(
                None,
                lambda: _run_produce_pipeline_sync(brief, job_dir),
            )
            relative_path = str(final_path.relative_to(Path(__file__).parent))
            set_job_output(job_id, relative_path)

            if warning and _app:
                await _app.bot.send_message(chat_id=chat_id, text=warning)
            if _app:
                with open(final_path, "rb") as f:
                    await _app.bot.send_video(
                        chat_id=chat_id, video=f, caption=caption,
                        read_timeout=120, write_timeout=120,
                    )

    except FATAL_ERRORS as e:
        msg = ERROR_MESSAGES.get(type(e), str(e))
        set_job_failed(job_id, str(e))
        logger.error(f"Job {job_id} failed: {e}")
        if _app:
            await _app.bot.send_message(chat_id=chat_id,
                                        text=f"{msg}\nJob ID: {job_id}")
    except Exception as e:
        set_job_failed(job_id, str(e))
        logger.exception(f"Unexpected error in job {job_id}")
        if _app:
            await _app.bot.send_message(chat_id=chat_id,
                                        text=f"Unexpected error. Job ID: {job_id}\n{str(e)[:200]}")


async def process_job(job: dict) -> None:
    """Process one job from the queue. Sends result to chat_id."""
    job_id = job["job_id"]
    command = job["command"]
    topic = job["topic"]
    chat_id = job["chat_id"]

    # Guard: new command types bypass ACCOUNT_DIR
    if command in ("brief", "produce"):
        await dispatch_brief_or_produce(job)
        return

    job_dir = config.OUTPUT_DIR / ACCOUNT_DIR[command] / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    update_job_status(job_id, "running")
    loop = asyncio.get_event_loop()

    try:
        pipeline_fn = PIPELINE_FN[command]
        final_path, caption, warning = await loop.run_in_executor(
            None, lambda: pipeline_fn(topic, job_dir)
        )

        relative_path = str(final_path.relative_to(Path(__file__).parent))
        set_job_output(job_id, relative_path)

        if warning and _app:
            await _app.bot.send_message(chat_id=chat_id, text=warning)

        if _app:
            with open(final_path, "rb") as f:
                await _app.bot.send_video(chat_id=chat_id, video=f, caption=caption, read_timeout=120, write_timeout=120)

    except FATAL_ERRORS as e:
        msg = ERROR_MESSAGES.get(type(e), str(e))
        set_job_failed(job_id, str(e))
        logger.error(f"Job {job_id} failed: {e}")
        if _app:
            await _app.bot.send_message(
                chat_id=chat_id,
                text=f"{msg}\nJob ID: {job_id}",
            )
    except Exception as e:
        set_job_failed(job_id, str(e))
        logger.exception(f"Unexpected error in job {job_id}")
        if _app:
            await _app.bot.send_message(
                chat_id=chat_id,
                text=f"Unexpected error. Job ID: {job_id}\n{str(e)[:200]}",
            )


async def queue_worker() -> None:
    """Background task: poll for pending jobs every 5 seconds."""
    while True:
        try:
            job = get_next_pending_job()
            if job:
                logger.info(f"Processing job {job['job_id']}: /{job['command']} \"{job['topic']}\"")
                await process_job(job)
        except Exception as e:
            logger.exception(f"Queue worker error: {e}")
        await asyncio.sleep(5)


# ── Command handlers ──────────────────────────────────────────────────────────

async def money_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: /money <topic>")
        return
    job_id = add_job("money", topic, chat_id=update.effective_chat.id)
    counts = get_status_counts()
    queue_pos = counts.get("pending", 0)
    await update.message.reply_text(
        f"Queued! Job ID: {job_id[:8]}\nTopic: {topic}\n"
        f"Position in queue: {queue_pos}\nEstimated time: ~4 min"
    )


async def b2b_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: /b2b <topic>")
        return
    job_id = add_job("b2b", topic, chat_id=update.effective_chat.id)
    counts = get_status_counts()
    queue_pos = counts.get("pending", 0)
    await update.message.reply_text(
        f"Queued! Job ID: {job_id[:8]}\nTopic: {topic}\n"
        f"Position in queue: {queue_pos}\nEstimated time: ~10 min"
    )


async def brief_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    topic = " ".join(context.args) if context.args else ""
    if not topic:
        await update.message.reply_text("Usage: /brief <topic>\nExample: /brief Jasper AI review")
        return
    job_id = add_brief_job(topic, chat_id=update.effective_chat.id)
    await update.message.reply_text(
        f"Generating brief for: {topic}\nJob ID: {job_id[:8]}\nEstimated time: ~30s"
    )


async def produce_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    raw = " ".join(context.args) if context.args else ""
    # Accept: "BR42", "#BR42", "42"
    clean = raw.lstrip("#").upper().lstrip("BR").strip()
    if not clean.isdigit():
        await update.message.reply_text("Usage: /produce BR42 (use the brief ID from /brief)")
        return
    brief_id = int(clean)
    brief = get_brief(brief_id)
    if brief is None:
        await update.message.reply_text(f"Brief #{brief_id} not found. Use /brief first.")
        return
    if brief["chat_id"] != update.effective_chat.id:
        return  # silent auth check
    job_id = add_produce_job(brief_id, chat_id=update.effective_chat.id)
    await update.message.reply_text(
        f"Queued produce job for Brief #{brief_id} ({brief['tool_name']})\n"
        f"Job ID: {job_id[:8]}\nEstimated time: ~5 min"
    )


async def assets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    args = context.args or []

    if len(args) == 0:
        # /assets — list all tools
        tools = list_tools()
        if not tools:
            await update.message.reply_text("No assets stored yet. Use /brief to start.")
            return
        lines = ["Asset library:"]
        for slug, count in tools:
            lines.append(f"  {slug}: {count} asset(s)")
        await update.message.reply_text("\n".join(lines))

    elif len(args) == 1 or (len(args) == 2 and args[1].lower() == "list"):
        # /assets jasper_ai  or  /assets jasper_ai list
        tool_slug = args[0]
        records = get_assets_for_tool(tool_slug)
        if not records:
            await update.message.reply_text(f"No assets for '{tool_slug}'.")
            return
        lines = [f"Assets for {tool_slug}:"]
        for r in records:
            hint = f" (scene {r.scene_hint})" if r.scene_hint else ""
            lines.append(f"  [{r.id}] {r.asset_type}{hint} — {r.created_at or 'unknown date'}")
        await update.message.reply_text("\n".join(lines))

    elif len(args) == 3 and args[1].lower() == "delete":
        # /assets jasper_ai delete 5
        tool_slug = args[0]
        if not args[2].isdigit():
            await update.message.reply_text("Usage: /assets <tool> delete <id>")
            return
        asset_id = int(args[2])
        ok = delete_asset(asset_id)
        if ok:
            await update.message.reply_text(f"Asset {asset_id} deleted.")
        else:
            await update.message.reply_text(f"Asset {asset_id} not found or could not be deleted.")
    else:
        await update.message.reply_text(
            "Usage:\n  /assets\n  /assets <tool>\n  /assets <tool> list\n  /assets <tool> delete <id>"
        )


async def file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo/video uploads — associate with the user's most recent brief."""
    if not is_authorized(update):
        return

    msg = update.message
    caption = msg.caption or ""
    chat_id = update.effective_chat.id

    # Parse brief_id from caption: "BR42", "#BR42", or fall back to most recent pending brief
    brief_id = None
    clean_cap = caption.strip().lstrip("#").upper()
    if clean_cap.startswith("BR") and clean_cap[2:].split()[0].isdigit():
        brief_id = int(clean_cap[2:].split()[0])
    elif clean_cap.isdigit():
        brief_id = int(clean_cap)
    else:
        pending = get_pending_brief_for_chat(chat_id)
        if pending:
            brief_id = pending["id"]

    if brief_id is None:
        await msg.reply_text("No active brief found. Send /brief <topic> first.")
        return

    brief = get_brief(brief_id)
    if brief is None:
        await msg.reply_text(f"Brief #{brief_id} not found.")
        return

    # Determine file type and get Telegram File object
    if msg.photo:
        tg_file = await msg.photo[-1].get_file()
        file_ext = ".jpg"
        asset_type = "screenshot"
    elif msg.video:
        tg_file = await msg.video.get_file()
        file_ext = ".mp4"
        asset_type = "screen_recording"
    elif msg.document:
        tg_file = await msg.document.get_file()
        fname = msg.document.file_name or ""
        file_ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ".bin"
        asset_type = "screenshot" if file_ext in (".png", ".jpg", ".jpeg") else "screen_recording"
    else:
        await msg.reply_text("Send a photo or video file.")
        return

    file_bytes = await tg_file.download_as_bytearray()

    # Parse scene hint from caption (e.g. "BR42 scene 2" or "scene 2")
    scene_hint = None
    scene_match = re.search(r"\bscene\s+(\d+)\b", caption, re.IGNORECASE)
    if scene_match:
        scene_hint = int(scene_match.group(1))

    record = store_asset(
        tool_slug=brief["tool_slug"],
        file_bytes=bytes(file_bytes),
        file_ext=file_ext,
        asset_type=asset_type,
        scene_hint=scene_hint,
        brief_id=brief_id,
    )

    hint_str = f" (scene {scene_hint})" if scene_hint else ""
    await msg.reply_text(
        f"✓ Asset received for {brief['tool_name']} (BR{brief_id}){hint_str}\n"
        f"Asset ID: {record.id}\n"
        f"When ready: /produce BR{brief_id}"
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    counts = get_status_counts()
    pending = counts.get("pending", 0)
    running = counts.get("running", 0)
    done = counts.get("done", 0)
    failed = counts.get("failed", 0)
    await update.message.reply_text(
        f"Queue status:\n"
        f"  Pending: {pending}\n"
        f"  Running: {running}\n"
        f"  Done: {done}\n"
        f"  Failed: {failed}"
    )


async def queue_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        return
    jobs = get_done_jobs()
    if not jobs:
        await update.message.reply_text("No completed clips yet.")
        return
    lines = ["Completed clips:"]
    for j in jobs[:10]:  # cap at 10
        lines.append(
            f"  [{j['job_id'][:8]}] /{j['command']} \"{j['topic']}\"\n"
            f"    → {j['output_path']}"
        )
    await update.message.reply_text("\n".join(lines))


# ── Startup ───────────────────────────────────────────────────────────────────

async def post_init(application: Application) -> None:
    global _app
    _app = application
    asyncio.create_task(queue_worker())
    logger.info("Queue worker started.")


def main() -> None:
    from queue_manager import recover_stuck_jobs
    init_db(DB_PATH)
    recover_stuck_jobs(DB_PATH)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("money", money_handler))
    app.add_handler(CommandHandler("b2b", b2b_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("queue", queue_list_handler))
    app.add_handler(CommandHandler("brief", brief_handler))
    app.add_handler(CommandHandler("produce", produce_handler))
    app.add_handler(CommandHandler("assets", assets_handler))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        file_upload_handler,
    ))

    logger.info("ClipBot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
