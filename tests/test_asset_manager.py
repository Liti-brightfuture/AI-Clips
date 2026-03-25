import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def make_db(tmp_path):
    db = str(tmp_path / "test.db")
    from queue_manager import init_db
    init_db(db)
    return db


def test_slugify():
    from pipeline.asset_manager import slugify
    assert slugify("Jasper AI") == "jasper_ai"
    assert slugify("Copy.ai") == "copy_ai"
    assert slugify("ElevenLabs") == "elevenlabs"
    assert slugify("  GPT-4o ") == "gpt_4o"


def test_store_asset_saves_file_and_db_record(tmp_path):
    from pipeline.asset_manager import store_asset
    db = make_db(tmp_path)
    assets_root = tmp_path / "assets" / "tools"
    assets_root.mkdir(parents=True)

    record = store_asset(
        tool_slug="jasper_ai",
        file_bytes=b"fake_png_data",
        file_ext=".png",
        asset_type="screenshot",
        scene_hint=1,
        brief_id=None,
        db_path=db,
        assets_root=str(assets_root),
    )

    assert record.id is not None
    assert Path(record.file_path).exists()
    assert Path(record.file_path).read_bytes() == b"fake_png_data"
    assert record.tool_slug == "jasper_ai"
    assert record.asset_type == "screenshot"
    assert record.scene_hint == 1


def test_get_assets_for_tool_returns_stored_records(tmp_path):
    from pipeline.asset_manager import store_asset, get_assets_for_tool
    db = make_db(tmp_path)
    assets_root = tmp_path / "assets" / "tools"
    assets_root.mkdir(parents=True)

    store_asset("jasper_ai", b"img1", ".png", "screenshot", 1, None, db, str(assets_root))
    store_asset("jasper_ai", b"img2", ".png", "screenshot", 2, None, db, str(assets_root))
    store_asset("copy_ai", b"img3", ".png", "screenshot", 1, None, db, str(assets_root))

    jasper_assets = get_assets_for_tool("jasper_ai", db)
    assert len(jasper_assets) == 2
    assert all(a.tool_slug == "jasper_ai" for a in jasper_assets)


def test_delete_asset_removes_file_and_record(tmp_path):
    from pipeline.asset_manager import store_asset, delete_asset, get_assets_for_tool
    db = make_db(tmp_path)
    assets_root = tmp_path / "assets" / "tools"
    assets_root.mkdir(parents=True)

    record = store_asset("jasper_ai", b"img", ".png", "screenshot", 1, None, db, str(assets_root))
    assert Path(record.file_path).exists()

    result = delete_asset(record.id, db)
    assert result is True
    assert not Path(record.file_path).exists()
    assert get_assets_for_tool("jasper_ai", db) == []


def test_delete_asset_returns_false_for_missing_id(tmp_path):
    from pipeline.asset_manager import delete_asset
    db = make_db(tmp_path)
    assert delete_asset(9999, db) is False


def test_list_tools_returns_counts(tmp_path):
    from pipeline.asset_manager import store_asset, list_tools
    db = make_db(tmp_path)
    assets_root = tmp_path / "assets" / "tools"
    assets_root.mkdir(parents=True)

    store_asset("jasper_ai", b"a", ".png", "screenshot", None, None, db, str(assets_root))
    store_asset("jasper_ai", b"b", ".mp4", "screen_recording", None, None, db, str(assets_root))
    store_asset("copy_ai", b"c", ".png", "screenshot", None, None, db, str(assets_root))

    tools = list_tools(db)
    tool_dict = {slug: count for slug, count in tools}
    assert tool_dict["jasper_ai"] == 2
    assert tool_dict["copy_ai"] == 1
