import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


def make_pexels_response(videos: list) -> dict:
    return {"videos": videos}


def make_video(width=1920, duration=15, link="http://example.com/clip.mp4"):
    return {
        "width": width,
        "duration": duration,
        "video_files": [{"link": link, "width": width, "height": 1080, "quality": "hd"}],
    }


def test_fetch_clips_returns_three_files(tmp_path):
    from pipeline.video_fetcher import fetch_clips
    keywords = ["AI tools", "laptop", "typing"]

    mock_search = MagicMock(return_value=make_pexels_response([make_video()]))
    mock_download = MagicMock(return_value=str(tmp_path / "clip_0.mp4"))

    with patch("pipeline.video_fetcher._search_pexels", mock_search), \
         patch("pipeline.video_fetcher._download_clip", mock_download):
        paths = fetch_clips(keywords, str(tmp_path), command="money")

    assert len(paths) == 3
    assert mock_search.call_count == 3


def test_fallback_keyword_used_on_empty(tmp_path):
    from pipeline.video_fetcher import fetch_clips

    def side_effect(keyword, api_key):
        if keyword in ("AI tools", "laptop", "typing"):
            return make_pexels_response([])
        return make_pexels_response([make_video()])

    mock_search = MagicMock(side_effect=side_effect)
    mock_download = MagicMock(return_value=str(tmp_path / "clip.mp4"))

    with patch("pipeline.video_fetcher._search_pexels", mock_search), \
         patch("pipeline.video_fetcher._download_clip", mock_download):
        paths = fetch_clips(["AI tools", "laptop", "typing"], str(tmp_path), command="money")

    assert len(paths) == 3


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
