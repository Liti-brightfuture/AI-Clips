import importlib
import os
import sys
import pytest


def reload_config(env_overrides: dict):
    """Helper: set env vars and re-import config."""
    for k, v in env_overrides.items():
        os.environ[k] = v
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config


FULL_ENV = {
    "OPENAI_API_KEY": "sk-test",
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "ELEVENLABS_API_KEY": "el-test",
    "ELEVENLABS_VOICE_ID": "voice123",
    "PEXELS_API_KEY": "px-test",
    "TAVILY_API_KEY": "tv-test",
    "GPT_RESEARCHER_PATH": "/tmp",
    "ALLOWED_CHAT_ID": "999",
}


def test_all_vars_present(tmp_path, monkeypatch):
    for k in FULL_ENV:
        monkeypatch.setenv(k, FULL_ENV[k])
    monkeypatch.setenv("GPT_RESEARCHER_PATH", str(tmp_path))
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    assert config.OPENAI_API_KEY == "sk-test"
    assert config.ALLOWED_CHAT_ID == 999  # parsed as int


def test_missing_var_exits(monkeypatch):
    for k in FULL_ENV:
        monkeypatch.setenv(k, FULL_ENV[k])
    monkeypatch.delenv("OPENAI_API_KEY")
    if "config" in sys.modules:
        del sys.modules["config"]
    try:
        with pytest.raises(SystemExit):
            import config
    finally:
        sys.modules.pop("config", None)  # always clean up to avoid contaminating other tests


def test_ffmpeg_missing_exits(monkeypatch, tmp_path):
    for k in FULL_ENV:
        monkeypatch.setenv(k, FULL_ENV[k])
    monkeypatch.setenv("GPT_RESEARCHER_PATH", str(tmp_path))
    if "config" in sys.modules:
        del sys.modules["config"]

    # Override the conftest autouse fixture: make ffmpeg check raise FileNotFoundError
    import subprocess as _subprocess
    original_run = _subprocess.run

    def ffmpeg_missing(cmd, *args, **kwargs):
        if isinstance(cmd, list) and "ffmpeg" in cmd:
            raise FileNotFoundError("ffmpeg not found")
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(_subprocess, "run", ffmpeg_missing)

    try:
        with pytest.raises(SystemExit):
            import config
    finally:
        sys.modules.pop("config", None)
