import subprocess
import sys

from pipeline.exceptions import ResearchError


def run_research(topic: str, gpt_researcher_path: str, timeout: int = 120) -> str:
    """
    Run GPT Researcher as a subprocess and return the research report.

    Args:
        topic: Research query string.
        gpt_researcher_path: Absolute path to the gpt-researcher directory.
        timeout: Seconds before subprocess is killed.

    Returns:
        Research report as a string (truncated to first 3000 chars).

    Raises:
        ResearchError: On non-zero exit code or timeout.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "cli.py", topic,
                "--report_type", "research_report",
                "--no-pdf", "--no-docx",
            ],
            cwd=gpt_researcher_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ResearchError(f"GPT Researcher timed out after {timeout}s for topic: '{topic}'")

    if result.returncode != 0:
        raise ResearchError(
            f"GPT Researcher exited with code {result.returncode}: {result.stderr[:500]}"
        )

    output = result.stdout.strip()
    return output[:3000]
