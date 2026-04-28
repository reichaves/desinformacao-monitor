"""
TikTok video collector using yt-dlp (hashtag and keyword search).

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: yt-dlp, subprocess, json
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from .base_collector import BaseCollector, VideoMetadata

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [3, 8, 15]


def _run_with_retry(cmd: list[str], retries: int = 3) -> subprocess.CompletedProcess:
    """Run a shell command with exponential-style retries."""
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


class TikTokCollector(BaseCollector):
    """
    Collects TikTok videos via yt-dlp hashtag/search pages.

    Requires cookies from a logged-in TikTok browser session.
    Set TIKTOK_COOKIES_FILE env var to a Netscape cookies.txt path.

    TikTok does not have a public API. This collector uses yt-dlp to
    fetch video lists from hashtag pages and downloads up to max_results.
    Note: TikTok actively blocks scrapers — failures are expected and logged.
    """

    PLATFORM = "tiktok"

    # TikTok hashtag page template
    _HASHTAG_URL = "https://www.tiktok.com/tag/{tag}"

    def __init__(self, output_dir: str, max_results: int = 20, cookies_file: Optional[str] = None):
        """
        Initialize the TikTok collector.

        Args:
            output_dir: Directory for downloaded files.
            max_results: Maximum videos to collect per run.
            cookies_file: Path to Netscape-format cookies.txt exported from
                          a logged-in TikTok browser session.
                          Falls back to TIKTOK_COOKIES_FILE env var.
        """
        super().__init__(output_dir, max_results)
        self.cookies_file = cookies_file or os.environ.get("TIKTOK_COOKIES_FILE")
        if self.cookies_file:
            logger.info("TikTok cookies loaded from: %s", self.cookies_file)
        else:
            logger.warning(
                "No TikTok cookies file — searches will likely fail. "
                "Set TIKTOK_COOKIES_FILE to a cookies.txt path."
            )

    def _cookies_args(self) -> list[str]:
        """Return yt-dlp --cookies argument if a cookies file is available."""
        if self.cookies_file and os.path.exists(self.cookies_file):
            return ["--cookies", self.cookies_file]
        return []

    def search(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Enumerate TikTok hashtag pages for videos matching the given queries.

        Args:
            queries: Hashtag names (with or without '#') or search terms.
            hours_back: Ignored for TikTok (no reliable timestamp in free scrape).

        Returns:
            List of VideoMetadata objects (url-only at this stage).
        """
        seen_ids: set[str] = set()
        results: list[VideoMetadata] = []

        for query in queries[:10]:
            tag = query.lstrip("#").replace(" ", "").lower()
            url = self._HASHTAG_URL.format(tag=tag)

            try:
                # Use yt-dlp to list up to 5 videos from the hashtag page
                cmd = [
                    "yt-dlp",
                    "--flat-playlist",
                    "--playlist-end", "5",
                    "--dump-json",
                    "--no-warnings",
                    "--quiet",
                    "--user-agent",
                    (
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                        "Version/17.0 Mobile/15E148 Safari/604.1"
                    ),
                    *self._cookies_args(),
                    url,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    logger.warning("TikTok search failed for tag '%s': %s", tag, result.stderr[:200])
                    continue

                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        info = json.loads(line)
                        vid_id = info.get("id") or info.get("webpage_url_basename", "")
                        vid_url = info.get("webpage_url") or info.get("url", "")
                        if not vid_id or vid_id in seen_ids or not vid_url:
                            continue
                        seen_ids.add(vid_id)

                        results.append(
                            VideoMetadata(
                                video_id=vid_id,
                                title=info.get("title", f"TikTok_{vid_id}"),
                                url=vid_url,
                                platform=self.PLATFORM,
                                channel=info.get("uploader", ""),
                                published_at=_ts_to_dt(info.get("timestamp")),
                                duration_seconds=int(info.get("duration") or 0),
                                view_count=int(info.get("view_count") or 0),
                                like_count=int(info.get("like_count") or 0),
                                description=info.get("description", ""),
                                keywords_matched=[query],
                            )
                        )
                    except json.JSONDecodeError:
                        continue

            except Exception as exc:
                logger.warning("TikTok search error for query '%s': %s", query, exc)

            time.sleep(2)  # rate limiting between hashtag pages

        logger.info("TikTok search found %d candidate videos", len(results))
        return results

    def download(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Download a TikTok video and extract MP3 audio.

        Args:
            metadata: VideoMetadata with a valid TikTok URL.

        Returns:
            Updated VideoMetadata with local_path and audio_path populated.
        """
        safe_id = metadata.video_id.replace("/", "_").replace("\\", "_")[:64]
        out_template = os.path.join(
            self.output_dir, f"{self.PLATFORM}_{safe_id}.%(ext)s"
        )

        video_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "best",
            "--output", out_template,
            "--user-agent",
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "--no-warnings",
            "--quiet",
            *self._cookies_args(),
            metadata.url,
        ]
        _run_with_retry(video_cmd)

        local_path = _find_file(
            self.output_dir,
            f"{self.PLATFORM}_{safe_id}",
            (".mp4", ".webm", ".mov"),
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
