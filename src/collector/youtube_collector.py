"""
YouTube video collector using yt-dlp for both search and download.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: yt-dlp, subprocess, json
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base_collector import BaseCollector, VideoMetadata

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [2, 5, 10]  # seconds between retries

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _run_with_retry(cmd: list[str], retries: int = 3) -> subprocess.CompletedProcess:
    """Run a shell command with exponential-style retries on failure."""
    last_exc: Optional[Exception] = None
    for attempt, delay in enumerate((_RETRY_DELAYS + [0])[:retries], start=1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                return result
            raise RuntimeError(f"yt-dlp exited {result.returncode}: {result.stderr[:400]}")
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                logger.warning("Attempt %d failed (%s). Retrying in %ds…", attempt, exc, delay)
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed") from last_exc


class YouTubeCollector(BaseCollector):
    """
    Collects YouTube videos matching disinformation-related queries.

    Uses yt-dlp's built-in ytsearch for discovery (no API key required)
    and yt-dlp for downloading video + audio extraction.
    """

    PLATFORM = "youtube"

    def search(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Search YouTube for recent videos matching the given queries.

        Uses yt-dlp ytsearchN: prefix to search without an API key.

        Args:
            queries: List of search strings / hashtags.
            hours_back: Approximate recency filter (best-effort).

        Returns:
            Deduplicated list of VideoMetadata sorted by view count descending.
        """
        seen_ids: set[str] = set()
        results: list[VideoMetadata] = []

        for query in queries[:15]:
            try:
                # ytsearch5: returns the top 5 results for the query
                cmd = [
                    "yt-dlp",
                    "--flat-playlist",
                    "--playlist-end", "5",
                    "--dump-json",
                    "--no-warnings",
                    "--quiet",
                    "--user-agent", _USER_AGENT,
                    f"ytsearch5:{query}",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    logger.warning(
                        "YouTube search failed for query '%s': %s",
                        query, result.stderr[:200],
                    )
                    continue

                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        info = json.loads(line)
                        vid_id = info.get("id", "")
                        if not vid_id or vid_id in seen_ids:
                            continue
                        seen_ids.add(vid_id)

                        duration = int(info.get("duration") or 0)
                        view_count = int(info.get("view_count") or 0)
                        like_count = int(info.get("like_count") or 0)
                        published_at = _ts_to_dt(info.get("timestamp"))

                        vid_url = (
                            info.get("webpage_url")
                            or f"https://www.youtube.com/watch?v={vid_id}"
                        )

                        results.append(
                            VideoMetadata(
                                video_id=vid_id,
                                title=info.get("title", ""),
                                url=vid_url,
                                platform=self.PLATFORM,
                                channel=info.get("channel") or info.get("uploader", ""),
                                published_at=published_at,
                                duration_seconds=duration,
                                view_count=view_count,
                                like_count=like_count,
                                description=info.get("description", "") or "",
                                keywords_matched=[query],
                            )
                        )
                    except json.JSONDecodeError:
                        continue

                time.sleep(1)  # rate limiting between searches

            except Exception as exc:
                logger.warning("YouTube search error for query '%s': %s", query, exc)

        results.sort(key=lambda v: v.view_count, reverse=True)
        logger.info("YouTube search found %d candidate videos", len(results))
        return results

    def download(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Download a YouTube video and extract MP3 audio with yt-dlp.

        Args:
            metadata: VideoMetadata with a valid YouTube URL.

        Returns:
            Updated VideoMetadata with local_path and audio_path populated.
        """
        safe_id = metadata.video_id.replace("/", "_").replace("\\", "_")
        out_template = os.path.join(self.output_dir, f"{self.PLATFORM}_{safe_id}.%(ext)s")

        video_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--output", out_template,
            "--user-agent", _USER_AGENT,
            "--no-warnings",
            "--quiet",
            metadata.url,
        ]
        _run_with_retry(video_cmd)

        local_path = _find_file(
            self.output_dir,
            f"{self.PLATFORM}_{safe_id}",
            (".mp4", ".mkv", ".webm"),
        )

        audio_path = os.path.join(self.output_dir, f"{self.PLATFORM}_{safe_id}.mp3")
        if local_path and not os.path.exists(audio_path):
            audio_cmd = [
                "ffmpeg", "-y", "-i", local_path,
                "-vn", "-acodec", "libmp3lame", "-ab", "96k",
                audio_path,
            ]
            _run_with_retry(audio_cmd)

        metadata.local_path = local_path
        metadata.audio_path = audio_path if os.path.exists(audio_path) else None
        return metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_to_dt(timestamp) -> Optional[datetime]:
    """Convert a Unix timestamp to a UTC datetime."""
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except Exception:
        return None


def _find_file(directory: str, prefix: str, extensions: tuple) -> Optional[str]:
    """Find the first file in `directory` matching prefix + one of the extensions."""
    for ext in extensions:
        candidate = os.path.join(directory, f"{prefix}{ext}")
        if os.path.exists(candidate):
            return candidate
    try:
        for fname in os.listdir(directory):
            if fname.startswith(prefix) and fname.endswith(extensions):
                return os.path.join(directory, fname)
    except Exception:
        pass
    return None
