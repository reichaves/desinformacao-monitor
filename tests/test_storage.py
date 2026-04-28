"""
Unit tests for the storage module.

Tests cover LocalStorage directory creation, JSON serialization,
and cleanup behaviour.

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
"""

import json
import os
import tempfile
import unittest

from src.storage.local_storage import LocalStorage


class TestLocalStorage(unittest.TestCase):
    """Tests for LocalStorage using a temporary base directory."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(base_dir=self.tmp_dir)

    def test_directories_created(self):
        self.assertTrue(os.path.isdir(self.storage.videos_dir))
        self.assertTrue(os.path.isdir(self.storage.screenshots_dir))
        self.assertTrue(os.path.isdir(self.storage.results_dir))
        self.assertTrue(os.path.isdir(self.storage.reports_dir))

    def test_screenshots_subdir_created(self):
        path = self.storage.screenshots_subdir("video123")
        self.assertTrue(os.path.isdir(path))
        self.assertIn("video123", path)

    def test_save_analysis_creates_json(self):
        data = {
            "video_id": "abc123",
            "platform": "youtube",
            "title": "Test Video",
            "severity": 2,
        }
        path = self.storage.save_analysis(data)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["video_id"], "abc123")

    def test_save_run_summary_creates_json(self):
        analyses = [{"video_id": "x1", "platform": "youtube", "severity": 1}]
        path = self.storage.save_run_summary(analyses)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            summary = json.load(f)
        self.assertEqual(summary["total_videos"], 1)
        self.assertIn("collected_at_utc", summary)

    def test_load_run_summary_returns_empty_when_missing(self):
        result = self.storage.load_run_summary()
        self.assertEqual(result, {})

    def test_cleanup_videos_removes_files(self):
        # Create a dummy file in videos_dir
        dummy = os.path.join(self.storage.videos_dir, "dummy.mp4")
        open(dummy, "w").close()
        self.assertTrue(os.path.exists(dummy))

        self.storage.cleanup_videos()
        self.assertFalse(os.path.exists(dummy))
        # The directory itself should still exist
        self.assertTrue(os.path.isdir(self.storage.videos_dir))

    def test_safe_id_for_slashes(self):
        """Video IDs with slashes should not create nested directories."""
        path = self.storage.screenshots_subdir("abc/def")
        self.assertTrue(os.path.isdir(path))
        self.assertNotIn("def", os.path.dirname(path))


if __name__ == "__main__":
    unittest.main()
