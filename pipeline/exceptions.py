class ScriptError(Exception):
    """Raised when GPT-4o script generation fails."""

class VoiceError(Exception):
    """Raised when ElevenLabs voice generation fails or limit is reached."""

class VideoFetchError(Exception):
    """Raised when Pexels cannot return usable stock footage."""

class TranscribeError(Exception):
    """Raised when Whisper transcription fails. Non-fatal — caught by queue worker."""

class AssembleError(Exception):
    """Raised when ffmpeg assembly fails."""

class ResearchError(Exception):
    """Raised when GPT Researcher subprocess fails or times out."""
