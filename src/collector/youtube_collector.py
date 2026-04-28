"""
YouTube video collector using youtubesearchpython + yt-dlp.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: youtubesearchpython, yt-dlp, subprocess
"""

import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from youtubesearchpython import VideosSearch

from .base_collector import BaseCollector, VideoMetadata

logger = logging.getLogger(__name__)

_YT_DLP_OPTS = [
    "--no-playlist",
    "--extract-audio",
    "--audio-format", "mp3",
    "--audio-quality", "96K",
    "--write-info-json",
    "--no-write-thumbnail",
    "--no-warnings",
    "--quiet",
    "--user-agent",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
]

_RETRY_DELAYS = [2, 5, 10]  # seconds between retries


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

    Uses youtubesearchpython for discovery (no API key required) and
    yt-dlp for downloading video + audio extraction.
    """

    PLATFORM = "youtube"

    def search(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Search YouTube for recent videos matching the given queries.

        Args:
            queries: List of search strings / hashtags.
            hours_back: Approximate recency filter (best-effort; YT search
                        does not expose precise publish timestamps in free mode).

        Returns:
            Deduplicated list of VideoMetadata sorted by view count descending.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        seen_ids: set[str] = set()
        results: list[VideoMetadata] = []

        # Limit queries to avoid hitting rate limits
        for query in queries[:15]:
            try:
                search = VideosSearch(query, limit=5)
                data = search.result()
                for item in data.get("result", []):
                    vid_id = item.get("id", "")
                    if not vid_id or vid_id in seen_ids:
                        continue
                    seen_ids.add(vid_id)

                    # Parse duration string "MM:SS" or "HH:MM:SS"
                    duration = _parse_duration(item.get("duration", "0:00"))

                    # Parse view count string "1,234 views"
                    views = _parse_count(item.get("viewCount", {}).get("text", "0"))

                    published_at = _parse_publish_time(item.get("publishedTime", ""))

                    results.append(
                        VideoMetadata(
                            video_id=vid_id,
                            title=item.get("title", ""),
                            url=f"https://www.youtube.com/watch?v={vid_id}",
                            platform=self.PLATFORM,
                            channel=item.get("channel", {}).get("name", ""),
                            published_at=published_at,
                            duration_seconds=duration,
                            view_count=views,
                            like_count=0,
                            description=item.get("descriptionSnippet", [{}])[0].get(
                                "text", ""
                            )
                            if item.get("descriptionSnippet")
                            else "",
                            keywords_matched=[query],
                        )
                    )
                time.sleep(1)  # rate limiting between searches
            except Exception as exc:
                logger.warning("YouTube search failed for query '%s': %s", query, exc)

        # Sort by view count descending and return unique results
        results.sort(key=lambda v: v.view_count, reverse=True)
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

        # First pass: download best video (for screenshots later)
        video_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--output", out_template,
            "--user-agent",
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "--no-warnings",
            "--quiet",
            metadata.url,
        ]
        _run_with_retry(video_cmd)

        # Locate downloaded video file
        local_path = _find_file(self.output_dir, f"{self.PLATFORM}_{safe_id}", (".mp4", ".mkv", ".webm"))

        # Second pass: extract audio
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

def _parse_duration(duration_str: str) -> int:
    """Convert 'MM:SS' or 'H:MM:SS' string to total seconds."""
    try:
        parts = [int(p) for p in duration_str.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 0


def _parse_count(text: str) -> int:
    """Parse strings like '1,234 views' or '1.2M views'."""
    try:
        text = text.lower().replace(",", "").replace("views", "").strip()
        if "m" in text:
            return int(float(text.replace("m", "")) * 1_000_000)
        if "k" in text:
            return int(float(text.replace("k", "")) * 1_000)
        return int(text)
    except Exception:
        return 0


def _parse_publish_time(text: str) -> Optional[datetime]:
    """
    Convert relative YouTube publish time text to approximate datetime.

    YouTube returns strings like '2 hours ago', '1 day ago'.
    Returns an approximate UTC datetime or None if unparseable.
    """
    try:
        text = text.lower().strip()
        now = datetime.now(timezone.utc)
        if "second" in text:
            n = int(text.split()[0])
            return now - timedelta(seconds=n)
        if "minute" in text:
            n = int(text.split()[0])
            return now - timedelta(minutes=n)
        if "hour" in text:
            n = int(text.split()[0])
            return now - timedelta(hours=n)
        if "day" in text:
            n = int(text.split()[0])
            return now - timedelta(days=n)
        if "week" in text:
            n = int(text.split()[0])
            return now - timedelta(weeks=n)
    except Exception:
        pass
    return None


def _find_file(directory: str, prefix: str, extensions: tuple) -> Optional[str]:
    """Find the first file in `directory` matching prefix + one of the extensions."""
    for ext in extensions:
        candidate = os.path.join(directory, f"{prefix}{ext}")
        if os.path.exists(candidate):
            return candidate
    # Fallback: glob
    try:
        for fname in os.listdir(directory):
            if fname.startswith(prefix) and fname.endswith(extensions):
                return os.path.join(directory, fname)
    except Exception:
        pass
    return None
