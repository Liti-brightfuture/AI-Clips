# tests/conftest.py
import subprocess
import pytest


@pytest.fixture(autouse=True)
def mock_ffmpeg_check(monkeypatch):
    """Prevent config.py's ffmpeg check from calling subprocess during tests."""
    original = subprocess.run

    def patched_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[:2] == ["ffmpeg", "-version"]:
            return subprocess.CompletedProcess(cmd, 0)
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", patched_run)
