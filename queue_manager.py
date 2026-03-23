import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent / "jobs.db")


def init_db(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT UNIQUE NOT NULL,
            command     TEXT NOT NULL,
            topic       TEXT NOT NULL,
            chat_id     INTEGER NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            output_path TEXT,
            error       TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            month      TEXT PRIMARY KEY,
            chars_used INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def recover_stuck_jobs(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "UPDATE jobs SET status='pending', updated_at=CURRENT_TIMESTAMP WHERE status='running'"
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    if count:
        logger.warning(f"Recovered {count} stuck job(s) to pending state.")
    return count


def add_job(command: str, topic: str, chat_id: int, db_path: str = DB_PATH) -> str:
    job_id = str(uuid4())
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (job_id, command, topic, chat_id) VALUES (?, ?, ?, ?)",
        (job_id, command, topic, chat_id),
    )
    conn.commit()
    conn.close()
    return job_id


def get_next_pending_job(db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_job(job_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_job_status(job_id: str, status: str, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
        (status, job_id),
    )
    conn.commit()
    conn.close()


def set_job_output(job_id: str, output_path: str, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET status='done', output_path=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
        (output_path, job_id),
    )
    conn.commit()
    conn.close()


def set_job_failed(job_id: str, error: str, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
        (error[:2000], job_id),
    )
    conn.commit()
    conn.close()


def get_status_counts(db_path: str = DB_PATH) -> Dict[str, int]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM jobs GROUP BY status"
    ).fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def get_done_jobs(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status='done' ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
