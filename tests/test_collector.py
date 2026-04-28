"""
Unit tests for the collector module.

Tests cover metadata helpers and the base collector contract.
Network calls are mocked.

Author: Abraji / reichaves
Date: 2026-04-28
"""

import json
import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.collector.base_collector import VideoMetadata
from src.collector.youtube_collector import YouTubeCollector, _ts_to_dt, _find_file


class TestTsToDt(unittest.TestCase):
    """Tests for Unix timestamp → datetime helper."""

    def test_valid_timestamp(self):
        dt = _ts_to_dt(0)
        self.assertEqual(dt, datetime(1970, 1, 1, tzinfo=timezone.utc))

    def test_invalid_returns_none(self):
        self.assertIsNone(_ts_to_dt(None))
        self.assertIsNone(_ts_to_dt("not-a-number"))
        self.assertIsNone(_ts_to_dt(""))


class TestVideoMetadata(unittest.TestCase):
    """Tests for the VideoMetadata dataclass."""

    def test_defaults(self):
        meta = VideoMetadata(
            video_id="abc123",
            title="Test",
            url="https://example.com",
            platform="youtube",
            channel="channel",
            published_at=None,
            duration_seconds=120,
            view_count=1000,
            like_count=50,
            description="desc",
        )
        self.assertEqual(meta.keywords_matched, [])
        self.assertIsNone(meta.local_path)
        self.assertIsNotNone(meta.collected_at)


class TestYouTubeCollectorSearch(unittest.TestCase):
    """Tests for YouTubeCollector.search() with mocked subprocess calls."""

    def _make_video_json(self, vid_id: str) -> str:
        return json.dumps({
            "id": vid_id,
            "title": f"Fake News {vid_id}",
            "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
            "channel": "Channel A",
            "duration": 90,
            "view_count": 5000,
            "like_count": 100,
            "timestamp": 1714294800,
            "description": "desc",
        })

    @patch("src.collector.youtube_collector.subprocess.run")
    def test_search_deduplicates_results(self, mock_run):
        """Duplicate video IDs across queries should appear only once."""
        # Both queries return the same video ID
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self._make_video_json("vid1")
        mock_run.return_value = mock_result

        collector = YouTubeCollector(output_dir="/tmp", max_results=5)
        results = collector.search(["query1", "query2"])

        ids = [r.video_id for r in results]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate IDs found in results")
        self.assertEqual(ids, ["vid1"])

    @patch("src.collector.youtube_collector.subprocess.run")
    def test_search_skips_failed_queries(self, mock_run):
        """Failed yt-dlp calls should be logged and skipped, not raise."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: some failure"
        mock_run.return_value = mock_result

        collector = YouTubeCollector(output_dir="/tmp", max_results=5)
        results = collector.search(["bad_query"])
        self.assertEqual(results, [])

    @patch("src.collector.youtube_collector.subprocess.run")
    def test_search_parses_metadata_correctly(self, mock_run):
        """Parsed VideoMetadata should reflect the yt-dlp JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self._make_video_json("abc123")
        mock_run.return_value = mock_result

        collector = YouTubeCollector(output_dir="/tmp", max_results=5)
        results = collector.search(["test"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].video_id, "abc123")
        self.assertEqual(results[0].view_count, 5000)
        self.assertEqual(results[0].platform, "youtube")


if __name__ == "__main__":
    unittest.main()
