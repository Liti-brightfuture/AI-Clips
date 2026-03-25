import os
from pathlib import Path
from typing import List, Optional

import requests

from pipeline.exceptions import VideoFetchError

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
FALLBACK_KEYWORDS = {
    "money": "technology",
    "b2b": "business office",
}
EXTRA_FALLBACKS = ["workspace", "office work"]
CLIP_TARGET = 25  # minimum unique clips to collect per video


def _search_pexels(keyword: str, api_key: str, per_page: int = 9) -> dict:
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": keyword, "per_page": per_page, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise VideoFetchError(f"Pexels search request failed for '{keyword}': {e}") from e


def _select_multiple_videos(videos: list, n: int) -> list:
    """Return up to n videos, preferring width >= 1080."""
    good = [v for v in videos if v.get("width", 0) >= 1080]
    rest = [v for v in videos if v.get("width", 0) < 1080]
    combined = good + rest
    return combined[:n]


def _get_download_link(video: dict) -> str:
    files = video.get("video_files", [])
    if not files:
        raise VideoFetchError("Video has no downloadable files.")
    for f in files:
        if f.get("quality") == "hd":
            return f["link"]
    return files[0]["link"]


def _download_clip(url: str, output_path: str) -> str:
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path
    except requests.exceptions.RequestException as e:
        raise VideoFetchError(f"Failed to download clip from '{url}': {e}") from e


def fetch_clips(
    keywords: List[str],
    output_dir: str,
    command: str,
    n_per_keyword: int = 9,
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Search Pexels for each keyword and download up to n_per_keyword clips each.
    Deduplicates by Pexels video ID across all keywords.
    Supplements with fallback keywords until 25 unique clips are reached.

    Args:
        keywords: List of search terms.
        output_dir: Directory to save raw clips (raw/ subfolder created inside).
        command: "money" or "b2b" (selects primary fallback keyword).
        n_per_keyword: Max clips per keyword (default 9 -> up to 27 total before dedup).
        api_key: Pexels API key (uses config if None).

    Returns:
        List of local file paths.

    Raises:
        VideoFetchError: If all keywords (including fallback) return no results.
    """
    if api_key is None:
        import config
        api_key = config.PEXELS_API_KEY

    raw_dir = Path(output_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    primary_fallback = FALLBACK_KEYWORDS.get(command, "technology")
    all_fallbacks = [primary_fallback] + EXTRA_FALLBACKS

    seen_ids: set = set()
    paths = []
    clip_index = 0

    def _collect_from_keyword(kw: str) -> None:
        nonlocal clip_index
        result = _search_pexels(kw, api_key, per_page=n_per_keyword)
        videos = _select_multiple_videos(result.get("videos", []), n_per_keyword)
        for video in videos:
            vid_id = video.get("id")
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            link = _get_download_link(video)
            out_path = str(raw_dir / f"clip_{clip_index}.mp4")
            paths.append(_download_clip(link, out_path))
            clip_index += 1

    for keyword in keywords:
        _collect_from_keyword(keyword)

    # Supplement with fallback keywords until we have at least CLIP_TARGET unique clips
    TARGET = CLIP_TARGET
    for fallback in all_fallbacks:
        if len(paths) >= TARGET:
            break
        _collect_from_keyword(fallback)

    if len(paths) == 0:
        raise VideoFetchError(
            "No stock footage found for any keyword including fallbacks."
        )

    return paths
