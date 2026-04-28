"""
Local file system management for temporary pipeline storage.

Creates per-run directories for raw downloads, screenshots, and results.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: os, json, datetime
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LocalStorage:
    """
    Manages the local directory structure for one pipeline run.

    Each run gets its own timestamped directory under `base_dir`:
        base_dir/
          YYYY-MM-DD_HHMMSS/
            videos/        ← downloaded video + audio files
            screenshots/   ← PNG frames (per-video subdirs)
            results/       ← JSON analysis results
            reports/       ← HTML report output
    """

    def __init__(self, base_dir: str):
        """
        Initialize storage for a new pipeline run.

        Args:
            base_dir: Root directory for all pipeline data.
        """
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        self.run_dir = os.path.join(base_dir, ts)
        self.videos_dir = os.path.join(self.run_dir, "videos")
        self.screenshots_dir = os.path.join(self.run_dir, "screenshots")
        self.results_dir = os.path.join(self.run_dir, "results")
        self.reports_dir = os.path.join(self.run_dir, "reports")

        for d in (self.videos_dir, self.screenshots_dir, self.results_dir, self.reports_dir):
            os.makedirs(d, exist_ok=True)

        logger.info("Local storage initialized at: %s", self.run_dir)

    def screenshots_subdir(self, video_id: str) -> str:
        """
        Return a dedicated screenshots subdirectory for one video.

        Creates the directory if it does not exist.

        Args:
            video_id: Unique video identifier.

        Returns:
            Absolute path to the screenshots subdirectory.
        """
        safe_id = video_id.replace("/", "_").replace("\\", "_")[:64]
        path = os.path.join(self.screenshots_dir, safe_id)
        os.makedirs(path, exist_ok=True)
        return path

    def save_analysis(self, analysis_dict: dict) -> str:
        """
        Write a single video's ContentAnalysis dict to a JSON file.

        Args:
            analysis_dict: Serializable dict from ContentAnalysis.to_dict().

        Returns:
            Path to the saved JSON file.
        """
        video_id = analysis_dict.get("video_id", "unknown")
        safe_id = video_id.replace("/", "_").replace("\\", "_")[:64]
        platform = analysis_dict.get("platform", "unknown")
        fname = f"{platform}_{safe_id}.json"
        path = os.path.join(self.results_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(analysis_dict, f, ensure_ascii=False, indent=2)
        logger.debug("Saved analysis: %s", path)
        return path

    def save_run_summary(self, analyses: list[dict]) -> str:
        """
        Write all analyses for this run to a single summary JSON file.

        Args:
            analyses: List of ContentAnalysis dicts.

        Returns:
            Path to the saved summary JSON file.
        """
        path = os.path.join(self.results_dir, "run_summary.json")
        summary = {
            "run_dir": self.run_dir,
            "collected_at_utc": datetime.now(timezone.utc).isoformat() + "Z",
            "total_videos": len(analyses),
            "videos": analyses,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info("Run summary saved: %s (%d videos)", path, len(analyses))
        return path

    def load_run_summary(self) -> dict:
        """
        Load the run summary JSON for this run.

        Returns:
            Parsed summary dict, or empty dict if not yet saved.
        """
        path = os.path.join(self.results_dir, "run_summary.json")
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def cleanup_videos(self) -> None:
        """
        Delete raw video and audio files to free disk space.

        Screenshots and JSON results are preserved.
        """
        try:
            shutil.rmtree(self.videos_dir, ignore_errors=True)
            os.makedirs(self.videos_dir, exist_ok=True)
            logger.info("Cleaned up downloaded video files from: %s", self.videos_dir)
        except Exception as exc:
            logger.warning("Could not clean up videos dir: %s", exc)
