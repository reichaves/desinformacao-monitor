"""
Abstract base class for video collectors.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: abc, dataclasses, logging
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Structured metadata for a collected video."""

    video_id: str
    title: str
    url: str
    platform: str
    channel: str
    published_at: Optional[datetime]
    duration_seconds: int
    view_count: int
    like_count: int
    description: str
    keywords_matched: list[str] = field(default_factory=list)
    local_path: Optional[str] = None
    audio_path: Optional[str] = None
    screenshots_dir: Optional[str] = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseCollector(ABC):
    """
    Abstract base class for platform-specific video collectors.

    Subclasses must implement `search` and `download`.
    """

    def __init__(self, output_dir: str, max_results: int = 20):
        """
        Initialize the collector.

        Args:
            output_dir: Directory where downloaded videos will be stored.
            max_results: Maximum number of videos to collect per run.
        """
        self.output_dir = output_dir
        self.max_results = max_results
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def search(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Search for videos matching the given queries.

        Args:
            queries: List of search terms or hashtags.
            hours_back: How many hours back to search.

        Returns:
            List of VideoMetadata objects for found videos.
        """

    @abstractmethod
    def download(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Download a video and extract its audio track.

        Args:
            metadata: VideoMetadata object with at minimum a valid URL.

        Returns:
            Updated VideoMetadata with local_path and audio_path set.
        """

    def collect(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Full collection cycle: search + download up to max_results videos.

        Args:
            queries: Search terms to use.
            hours_back: Time window in hours.

        Returns:
            List of VideoMetadata objects with local files ready for processing.
        """
        self.logger.info(
            "Starting collection with %d queries, window=%dh, max=%d",
            len(queries),
            hours_back,
            self.max_results,
        )

        found = self.search(queries, hours_back)
        self.logger.info("Found %d candidate videos", len(found))

        downloaded: list[VideoMetadata] = []
        for meta in found[: self.max_results]:
            try:
                meta = self.download(meta)
                downloaded.append(meta)
                self.logger.info("Downloaded: %s (%s)", meta.title, meta.video_id)
            except Exception as exc:
                self.logger.error(
                    "Failed to download %s: %s", meta.video_id, exc, exc_info=True
                )

        self.logger.info("Collection complete: %d/%d downloaded", len(downloaded), len(found))
        return downloaded
