import asyncio
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_jobs.db")
    from queue_manager import init_db
    init_db(path)
    return path


def test_init_creates_tables(db_path):
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "jobs" in tables
    assert "usage" in tables
    conn.close()


def test_add_job_returns_job_id(db_path):
    from queue_manager import add_job
    job_id = add_job("money", "Jasper AI", chat_id=123, db_path=db_path)
    assert job_id is not None
    assert len(job_id) == 36  # UUID4


def test_get_next_pending_job(db_path):
    from queue_manager import add_job, get_next_pending_job
    add_job("money", "Topic A", chat_id=123, db_path=db_path)
    job = get_next_pending_job(db_path)
    assert job is not None
    assert job["topic"] == "Topic A"
    assert job["status"] == "pending"


def test_update_job_status(db_path):
    from queue_manager import add_job, update_job_status, get_job
    job_id = add_job("money", "Topic B", chat_id=123, db_path=db_path)
    update_job_status(job_id, "running", db_path=db_path)
    job = get_job(job_id, db_path)
    assert job["status"] == "running"


def test_crash_recovery_resets_running_to_pending(db_path):
    from queue_manager import add_job, update_job_status, recover_stuck_jobs, get_job
    job_id = add_job("money", "Stuck job", chat_id=123, db_path=db_path)
    update_job_status(job_id, "running", db_path=db_path)
    recover_stuck_jobs(db_path)
    job = get_job(job_id, db_path)
    assert job["status"] == "pending"


def test_get_status_counts(db_path):
    from queue_manager import add_job, update_job_status, get_status_counts
    j1 = add_job("money", "T1", chat_id=1, db_path=db_path)
    j2 = add_job("b2b", "T2", chat_id=1, db_path=db_path)
    update_job_status(j2, "done", db_path=db_path)
    counts = get_status_counts(db_path)
    assert counts["pending"] == 1
    assert counts["done"] == 1


def test_get_done_jobs(db_path):
    from queue_manager import add_job, update_job_status, set_job_output, get_done_jobs
    j1 = add_job("money", "T1", chat_id=1, db_path=db_path)
    set_job_output(j1, "output/clips/account1/j1/final.mp4", db_path=db_path)
    jobs = get_done_jobs(db_path)
    assert len(jobs) == 1
    assert jobs[0]["output_path"] == "output/clips/account1/j1/final.mp4"
