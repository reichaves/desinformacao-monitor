"""
Unit tests for the collector module.

Tests cover keyword parsing, duration/count helpers, and the base collector
contract. Actual network calls are mocked.

Author: Abraji / reichaves
Date: 2026-04-28
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.collector.base_collector import VideoMetadata
from src.collector.youtube_collector import (
    YouTubeCollector,
    _parse_count,
    _parse_duration,
    _parse_publish_time,
)


class TestParseHelpers(unittest.TestCase):
    """Tests for YouTube collector helper functions."""

    def test_parse_duration_mm_ss(self):
        self.assertEqual(_parse_duration("3:45"), 225)

    def test_parse_duration_hh_mm_ss(self):
        self.assertEqual(_parse_duration("1:02:30"), 3750)

    def test_parse_duration_invalid(self):
        self.assertEqual(_parse_duration(""), 0)
        self.assertEqual(_parse_duration("live"), 0)

    def test_parse_count_views_string(self):
        self.assertEqual(_parse_count("1,234 views"), 1234)
        self.assertEqual(_parse_count("2.5M views"), 2_500_000)
        self.assertEqual(_parse_count("10K views"), 10_000)
        self.assertEqual(_parse_count("0"), 0)

    def test_parse_publish_time_hours(self):
        result = _parse_publish_time("3 hours ago")
        self.assertIsNotNone(result)
        # Should be approximately 3 hours in the past
        delta = datetime.now(timezone.utc) - result
        self.assertAlmostEqual(delta.total_seconds() / 3600, 3, delta=0.1)

    def test_parse_publish_time_days(self):
        result = _parse_publish_time("2 days ago")
        self.assertIsNotNone(result)
        delta = datetime.now(timezone.utc) - result
        self.assertAlmostEqual(delta.total_seconds() / 86400, 2, delta=0.1)

    def test_parse_publish_time_invalid(self):
        self.assertIsNone(_parse_publish_time("streamed live"))
        self.assertIsNone(_parse_publish_time(""))


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
    """Tests for YouTubeCollector.search() with mocked HTTP responses."""

    @patch("src.collector.youtube_collector.VideosSearch")
    def test_search_deduplicates_results(self, mock_videos_search):
        """Duplicate video IDs should appear only once in results."""
        mock_instance = MagicMock()
        mock_instance.result.return_value = {
            "result": [
                {
                    "id": "vid1",
                    "title": "Fake News Alert",
                    "duration": "1:30",
                    "viewCount": {"text": "5,000 views"},
                    "publishedTime": "2 hours ago",
                    "channel": {"name": "Channel A"},
                    "descriptionSnippet": None,
                }
            ]
        }
        mock_videos_search.return_value = mock_instance

        collector = YouTubeCollector(output_dir="/tmp", max_results=5)
        results = collector.search(["query1", "query2"])

        # "vid1" appears in both queries but should only be returned once
        ids = [r.video_id for r in results]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate IDs found in results")


if __name__ == "__main__":
    unittest.main()
