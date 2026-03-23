import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "PEXELS_API_KEY",
    "TAVILY_API_KEY",
    "GPT_RESEARCHER_PATH",
    "ALLOWED_CHAT_ID",
]

missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    print(f"[config] Missing required env vars: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
ELEVENLABS_API_KEY: str = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID: str = os.environ["ELEVENLABS_VOICE_ID"]
PEXELS_API_KEY: str = os.environ["PEXELS_API_KEY"]
TAVILY_API_KEY: str = os.environ["TAVILY_API_KEY"]
GPT_RESEARCHER_PATH: str = os.environ["GPT_RESEARCHER_PATH"]
try:
    ALLOWED_CHAT_ID: int = int(os.environ["ALLOWED_CHAT_ID"])
except ValueError:
    print("[config] ALLOWED_CHAT_ID must be an integer.", file=sys.stderr)
    sys.exit(1)

# Validate GPT_RESEARCHER_PATH exists
if not Path(GPT_RESEARCHER_PATH).is_dir():
    print(f"[config] GPT_RESEARCHER_PATH does not exist: {GPT_RESEARCHER_PATH}", file=sys.stderr)
    sys.exit(1)

# Validate ffmpeg is in PATH
try:
    subprocess.run(
        ["ffmpeg", "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
except (FileNotFoundError, subprocess.CalledProcessError):
    print("[config] ffmpeg not found in PATH. Install ffmpeg and ensure it is accessible.", file=sys.stderr)
    sys.exit(1)

# Output base directory (relative paths stored in DB)
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output" / "clips"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "logs").mkdir(exist_ok=True)
