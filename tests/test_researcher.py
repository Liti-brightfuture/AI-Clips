import sys
import pytest
from unittest.mock import MagicMock, patch


def test_returns_truncated_output(tmp_path):
    from researcher import run_research
    long_output = "A" * 5000
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = long_output

    with patch("researcher.subprocess.run", return_value=mock_result):
        result = run_research("HubSpot vs Monday", str(tmp_path))

    assert len(result) == 3000
    assert result == "A" * 3000


def test_nonzero_exit_raises_research_error(tmp_path):
    from researcher import run_research
    from pipeline.exceptions import ResearchError
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Connection error"

    with patch("researcher.subprocess.run", return_value=mock_result):
        with pytest.raises(ResearchError, match="exited with code 1"):
            run_research("some topic", str(tmp_path))


def test_timeout_raises_research_error(tmp_path):
    from researcher import run_research
    from pipeline.exceptions import ResearchError
    import subprocess

    with patch("researcher.subprocess.run", side_effect=subprocess.TimeoutExpired("cli.py", 120)):
        with pytest.raises(ResearchError, match="timed out"):
            run_research("some topic", str(tmp_path))


def test_uses_sys_executable(tmp_path):
    from researcher import run_research
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "research output"

    with patch("researcher.subprocess.run", return_value=mock_result) as mock_run:
        run_research("test topic", str(tmp_path))

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == sys.executable


def test_includes_no_pdf_no_docx_flags(tmp_path):
    from researcher import run_research
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "output"

    with patch("researcher.subprocess.run", return_value=mock_result) as mock_run:
        run_research("test topic", str(tmp_path))

    cmd = mock_run.call_args[0][0]
    assert "--no-pdf" in cmd
    assert "--no-docx" in cmd
