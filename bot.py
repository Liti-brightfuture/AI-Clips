import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from queue_manager import (
    init_db, add_job, get_next_pending_job, update_job_status,
    set_job_output, set_job_failed, get_status_counts, get_done_jobs, DB_PATH,
)
from pipeline.script_generator import generate_script
from pipeline.voice_generator import generate_voice
from pipeline.video_fetcher import fetch_clips
from pipeline.transcriber import transcribe
from pipeline.assembler import assemble
from pipeline.sfx_fetcher import get_sfx_cues
from pipeline.assembler import get_audio_duration
from pipeline.caption_generator import generate_caption
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


async def process_job(job: dict) -> None:
    """Process one job from the queue. Sends result to chat_id."""
    job_id = job["job_id"]
    command = job["command"]
    topic = job["topic"]
    chat_id = job["chat_id"]

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
                await _app.bot.send_video(chat_id=chat_id, video=f, caption=caption)

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

    logger.info("ClipBot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
