import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

DB_PATH_DEFAULT = str(Path(__file__).parent.parent / "jobs.db")
ASSETS_ROOT_DEFAULT = str(Path(__file__).parent.parent / "assets" / "tools")


@dataclass
class AssetRecord:
    id: Optional[int]
    tool_slug: str
    file_path: str
    asset_type: str       # "screenshot" | "screen_recording"
    scene_hint: Optional[int]
    brief_id: Optional[int]
    created_at: Optional[str]


def slugify(name: str) -> str:
    """Convert 'Jasper AI' -> 'jasper_ai'."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


def store_asset(
    tool_slug: str,
    file_bytes: bytes,
    file_ext: str,
    asset_type: str,
    scene_hint: Optional[int],
    brief_id: Optional[int],
    db_path: str = DB_PATH_DEFAULT,
    assets_root: str = ASSETS_ROOT_DEFAULT,
) -> AssetRecord:
    """Save asset bytes to disk and record in SQLite. Returns AssetRecord with id set."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = str(uuid4())[:8]
    filename = f"{ts}_{uid}{file_ext}"
    dest_dir = Path(assets_root) / tool_slug / asset_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    dest_path.write_bytes(file_bytes)

    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO tool_assets (tool_slug, file_path, asset_type, scene_hint, brief_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (tool_slug, str(dest_path), asset_type, scene_hint, brief_id),
    )
    asset_id = cur.lastrowid
    conn.commit()
    conn.close()

    return AssetRecord(
        id=asset_id,
        tool_slug=tool_slug,
        file_path=str(dest_path),
        asset_type=asset_type,
        scene_hint=scene_hint,
        brief_id=brief_id,
        created_at=None,
    )


def get_assets_for_tool(tool_slug: str, db_path: str = DB_PATH_DEFAULT) -> List[AssetRecord]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM tool_assets WHERE tool_slug=? ORDER BY created_at",
        (tool_slug,),
    ).fetchall()
    conn.close()
    return [_row_to_record(r) for r in rows]


def get_assets_for_brief(brief_id: int, db_path: str = DB_PATH_DEFAULT) -> List[AssetRecord]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM tool_assets WHERE brief_id=? ORDER BY scene_hint, created_at",
        (brief_id,),
    ).fetchall()
    conn.close()
    return [_row_to_record(r) for r in rows]


def delete_asset(asset_id: int, db_path: str = DB_PATH_DEFAULT) -> bool:
    """Delete asset file then SQLite record. Returns True on success."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tool_assets WHERE id=?", (asset_id,)).fetchone()
    conn.close()
    if row is None:
        return False
    try:
        os.remove(row["file_path"])
    except OSError as e:
        logger.warning(f"Could not delete asset file {row['file_path']}: {e}")
        return False
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM tool_assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()
    return True


def list_tools(db_path: str = DB_PATH_DEFAULT) -> List[tuple]:
    """Return list of (tool_slug, count) tuples."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT tool_slug, COUNT(*) FROM tool_assets GROUP BY tool_slug ORDER BY tool_slug"
    ).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def _row_to_record(row) -> AssetRecord:
    return AssetRecord(
        id=row["id"],
        tool_slug=row["tool_slug"],
        file_path=row["file_path"],
        asset_type=row["asset_type"],
        scene_hint=row["scene_hint"],
        brief_id=row["brief_id"],
        created_at=row["created_at"],
    )
