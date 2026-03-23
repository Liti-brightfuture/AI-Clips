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


def _search_pexels(keyword: str, api_key: str) -> dict:
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": keyword, "per_page": 10, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise VideoFetchError(f"Pexels search request failed for '{keyword}': {e}") from e


def _select_best_video(videos: list) -> Optional[dict]:
    if not videos:
        return None
    # Prefer width >= 1080; fall back to first result
    for v in videos:
        if v.get("width", 0) >= 1080:
            return v
    return videos[0]


def _get_download_link(video: dict) -> str:
    files = video.get("video_files", [])
    if not files:
        raise VideoFetchError("Video has no downloadable files.")
    # Prefer hd quality
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
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Search Pexels for each keyword and download one clip per keyword.

    Args:
        keywords: List of 3 search terms.
        output_dir: Directory to save raw clips (raw/ subfolder created inside).
        command: "money" or "b2b" (selects fallback keyword).
        api_key: Pexels API key (uses config if None).

    Returns:
        List of local file paths (up to 3 clips).

    Raises:
        VideoFetchError: If all keywords (including fallback) return no results.
    """
    if api_key is None:
        import config
        api_key = config.PEXELS_API_KEY

    raw_dir = Path(output_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fallback = FALLBACK_KEYWORDS.get(command, "technology")
    paths = []
    fallback_result: Optional[dict] = None  # cached fallback to avoid redundant API calls

    for i, keyword in enumerate(keywords):
        result = _search_pexels(keyword, api_key)
        videos = result.get("videos", [])
        video = _select_best_video(videos)

        if video is None:
            if fallback_result is None:
                fallback_result = _search_pexels(fallback, api_key)
            videos = fallback_result.get("videos", [])
            video = _select_best_video(videos)

        if video is None:
            raise VideoFetchError(
                f"No stock footage found for '{keyword}' or fallback '{fallback}'."
            )

        link = _get_download_link(video)
        out_path = str(raw_dir / f"clip_{i}.mp4")
        _download_clip(link, out_path)
        paths.append(out_path)

    return paths
