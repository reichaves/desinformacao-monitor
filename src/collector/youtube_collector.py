"""
YouTube video collector using yt-dlp for search and youtube-transcript-api
for transcription. Video download is attempted but gracefully skipped when
blocked by bot detection (common on cloud/datacenter IPs).

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
Dependencies: yt-dlp, youtube-transcript-api, subprocess, json
"""

import io
import json
import logging
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
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

    Supports cookie-based authentication to bypass bot detection on
    GitHub Actions IPs. Pass cookies_file path or set YOUTUBE_COOKIES_FILE
    environment variable.
    """

    PLATFORM = "youtube"

    def __init__(self, output_dir: str, max_results: int = 20, cookies_file: Optional[str] = None):
        """
        Initialize the YouTube collector.

        Args:
            output_dir: Directory for downloaded files.
            max_results: Maximum videos to collect per run.
            cookies_file: Path to Netscape-format cookies.txt file.
                          Falls back to YOUTUBE_COOKIES_FILE env var.
        """
        super().__init__(output_dir, max_results)
        self.cookies_file = cookies_file or os.environ.get("YOUTUBE_COOKIES_FILE")
        if self.cookies_file:
            logger.info("YouTube cookies loaded from: %s", self.cookies_file)
        else:
            logger.warning(
                "No YouTube cookies file — downloads may be blocked on cloud IPs. "
                "Set YOUTUBE_COOKIES_FILE to a cookies.txt path."
            )

    def _cookies_args(self) -> list[str]:
        """Return yt-dlp --cookies argument if a cookies file is available."""
        if self.cookies_file and os.path.exists(self.cookies_file):
            return ["--cookies", self.cookies_file]
        return []

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
                    *self._cookies_args(),
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

    def fetch_transcript(self, video_id: str) -> Optional[str]:
        """
        Fetch auto-generated captions for a YouTube video using youtube-transcript-api.

        Does not require video download and works from any IP address.

        Args:
            video_id: YouTube video ID (e.g. "dQw4w9WgXcQ").

        Returns:
            Full transcript as a single string, or None if unavailable.
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            # Prefer Portuguese; fall back to any available language
            try:
                transcript = transcript_list.find_transcript(["pt", "pt-BR", "pt-PT"])
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(["pt", "pt-BR", "en", "es"])
                except NoTranscriptFound:
                    transcript = next(iter(transcript_list))
            entries = transcript.fetch()
            text = " ".join(e.get("text", "") for e in entries)
            logger.info("Fetched transcript for %s (%d chars)", video_id, len(text))
            return text.strip() or None
        except Exception as exc:
            logger.warning("Could not fetch transcript for %s: %s", video_id, exc)
            return None

    def fetch_thumbnail(self, video_id: str, output_dir: str) -> Optional[str]:
        """
        Download the highest-resolution YouTube thumbnail available.

        Tries maxresdefault → hqdefault → mqdefault in order.

        Args:
            video_id: YouTube video ID.
            output_dir: Directory to save the thumbnail file.

        Returns:
            Path to saved thumbnail PNG, or None on failure.
        """
        thumb_path = os.path.join(output_dir, f"{self.PLATFORM}_{video_id}_thumb.jpg")
        if os.path.exists(thumb_path):
            return thumb_path
        for quality in ("maxresdefault", "hqdefault", "mqdefault"):
            url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                # YouTube returns a 120×90 placeholder for missing qualities — skip it
                if len(data) < 5000:
                    continue
                with open(thumb_path, "wb") as f:
                    f.write(data)
                logger.info("Downloaded thumbnail for %s (%s)", video_id, quality)
                return thumb_path
            except Exception as exc:
                logger.debug("Thumbnail %s failed for %s: %s", quality, video_id, exc)
        return None

    def download(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Attempt to download a YouTube video; fall back to transcript API + thumbnail.

        Primary path: yt-dlp video + ffmpeg audio extraction.
        Fallback (e.g. bot-detection on cloud IPs): youtube-transcript-api captions
        and thumbnail image — no video file needed.

        Args:
            metadata: VideoMetadata with a valid YouTube URL.

        Returns:
            Updated VideoMetadata. If download succeeds: local_path and audio_path
            are set. If download fails: prefetched_transcript and thumbnail_paths
            are set instead.
        """
        safe_id = metadata.video_id.replace("/", "_").replace("\\", "_")
        out_template = os.path.join(self.output_dir, f"{self.PLATFORM}_{safe_id}.%(ext)s")

        video_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--output", out_template,
            "--user-agent", _USER_AGENT,
            "--no-warnings",
            "--quiet",
            *self._cookies_args(),
            metadata.url,
        ]
        try:
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
        except Exception as exc:
            logger.warning(
                "Video download failed for %s (%s) — using transcript API + thumbnail fallback.",
                metadata.video_id, exc,
            )
            # Fallback: captions + thumbnail (no video file)
            transcript = self.fetch_transcript(metadata.video_id)
            if transcript:
                metadata.prefetched_transcript = transcript
            thumb = self.fetch_thumbnail(metadata.video_id, self.output_dir)
            if thumb:
                metadata.thumbnail_paths = [thumb]

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
