import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


def make_pexels_response(videos: list) -> dict:
    return {"videos": videos}


def make_video(width=1920, duration=15, link="http://example.com/clip.mp4"):
    return {
        "id": 1,
        "width": width,
        "duration": duration,
        "video_files": [{"link": link, "width": width, "height": 1080, "quality": "hd"}],
    }


def test_fetch_clips_returns_three_files(tmp_path):
    from pipeline.video_fetcher import fetch_clips
    keywords = ["AI tools", "laptop", "typing"]

    # Primary keywords return IDs 0, 1, 2 (unique).
    # Fallback keywords return ID=0 (already seen) -> deduplicated out -> still 3 clips total.
    def search_side_effect(keyword, api_key, per_page=9):
        vid_map = {"AI tools": 0, "laptop": 1, "typing": 2}
        vid_id = vid_map.get(keyword, 0)  # fallbacks return ID=0, already seen
        return make_pexels_response([make_video_with_id(vid_id)])

    paths_returned = [str(tmp_path / f"clip_{i}.mp4") for i in range(3)]
    mock_download = MagicMock(side_effect=paths_returned)

    with patch("pipeline.video_fetcher._search_pexels", side_effect=search_side_effect), \
         patch("pipeline.video_fetcher._download_clip", mock_download):
        paths = fetch_clips(keywords, str(tmp_path), command="money")

    assert len(paths) == 3
    assert len(set(paths)) == 3


def test_fallback_keyword_used_on_empty(tmp_path):
    from pipeline.video_fetcher import fetch_clips

    def side_effect(keyword, api_key, per_page=9):
        if keyword in ("AI tools", "laptop", "typing"):
            return make_pexels_response([])
        # Fallback keywords return a valid video
        return make_pexels_response([make_video_with_id(99)])

    mock_search = MagicMock(side_effect=side_effect)
    mock_download = MagicMock(return_value=str(tmp_path / "clip.mp4"))

    with patch("pipeline.video_fetcher._search_pexels", mock_search), \
         patch("pipeline.video_fetcher._download_clip", mock_download):
        paths = fetch_clips(["AI tools", "laptop", "typing"], str(tmp_path), command="money")

    assert len(paths) >= 1
    # Fallback was called (more than 3 primary calls)
    assert mock_search.call_count > 3


def test_raises_when_fallback_also_fails(tmp_path):
    from pipeline.video_fetcher import fetch_clips
    from pipeline.exceptions import VideoFetchError

    mock_search = MagicMock(return_value=make_pexels_response([]))
    with patch("pipeline.video_fetcher._search_pexels", mock_search):
        with pytest.raises(VideoFetchError):
            fetch_clips(["bad keyword"], str(tmp_path), command="money")


def test_selects_video_with_width_gte_1080(tmp_path):
    from pipeline.video_fetcher import _select_best_video
    videos = [
        make_video(width=640),
        make_video(width=1920, link="http://example.com/hd.mp4"),
    ]
    selected = _select_best_video(videos)
    assert selected["video_files"][0]["link"] == "http://example.com/hd.mp4"


def test_raises_on_empty_video_files(tmp_path):
    from pipeline.video_fetcher import fetch_clips
    from pipeline.exceptions import VideoFetchError

    empty_files_video = {"width": 1920, "duration": 15, "video_files": []}
    mock_search = MagicMock(return_value=make_pexels_response([empty_files_video]))

    with patch("pipeline.video_fetcher._search_pexels", mock_search):
        with pytest.raises(VideoFetchError):
            fetch_clips(["AI tools"], str(tmp_path), command="money")


def make_video_with_id(vid_id: int, width=1920, link=None):
    return {
        "id": vid_id,
        "width": width,
        "duration": 15,
        "video_files": [{"link": link or f"http://example.com/clip_{vid_id}.mp4",
                          "width": width, "height": 1080, "quality": "hd"}],
    }


def test_fetch_clips_returns_up_to_27_unique_files_when_all_keywords_full(tmp_path):
    """When each keyword returns 9 unique videos, all 27 are fetched (exceeds 25 target)."""
    from pipeline.video_fetcher import fetch_clips
    keywords = ["AI tools", "laptop", "typing"]

    def search_side_effect(keyword, api_key, per_page=9):
        base = {"AI tools": 0, "laptop": 9, "typing": 18}
        offset = base.get(keyword, 0)
        return {"videos": [make_video_with_id(offset + i) for i in range(9)]}

    downloaded = []
    def download_side_effect(url, path):
        downloaded.append(path)
        return path

    with patch("pipeline.video_fetcher._search_pexels", side_effect=search_side_effect), \
         patch("pipeline.video_fetcher._download_clip", side_effect=download_side_effect):
        paths = fetch_clips(keywords, str(tmp_path), command="money")

    assert len(paths) == 27  # 9 per keyword, all unique IDs
    assert len(set(paths)) == len(paths)


def test_fetch_clips_supplements_with_fallback_to_reach_25(tmp_path):
    """When primary keywords return fewer than 25 clips, fallback keywords supplement."""
    from pipeline.video_fetcher import fetch_clips

    def search_side_effect(keyword, api_key, per_page=9):
        kw_map = {"AI tools": 0, "laptop": 3, "typing": 6}
        fallback_base = {"technology": 100, "office work": 110}
        if keyword in kw_map:
            offset = kw_map[keyword]
            return {"videos": [make_video_with_id(offset + i) for i in range(3)]}
        offset = fallback_base.get(keyword, 200)
        return {"videos": [make_video_with_id(offset + i) for i in range(9)]}

    downloaded_paths = []
    def download_side_effect(url, path):
        downloaded_paths.append(path)
        return path

    with patch("pipeline.video_fetcher._search_pexels", side_effect=search_side_effect), \
         patch("pipeline.video_fetcher._download_clip", side_effect=download_side_effect):
        paths = fetch_clips(["AI tools", "laptop", "typing"], str(tmp_path), command="money")

    # Primary keywords gave 9 unique clips; fallback should supplement to >=25
    assert len(paths) >= 25
    assert len(set(paths)) == len(paths)  # no duplicate paths


def test_fetch_clips_deduplicates_by_pexels_id(tmp_path):
    from pipeline.video_fetcher import fetch_clips

    duplicate_videos = [make_video_with_id(i) for i in range(5)]

    def search_side_effect(keyword, api_key, per_page=9):
        return {"videos": duplicate_videos}

    downloaded = []
    def download_side_effect(url, path):
        downloaded.append(path)
        return path

    with patch("pipeline.video_fetcher._search_pexels", side_effect=search_side_effect), \
         patch("pipeline.video_fetcher._download_clip", side_effect=download_side_effect):
        paths = fetch_clips(["k1", "k2", "k3"], str(tmp_path), command="money")

    # Only 5 unique IDs despite 3 keywords + fallbacks returning same 5 videos
    assert len(paths) == 5
