"""
TikTok video collector using Playwright for browser-based scraping + yt-dlp for download.

yt-dlp's TikTok hashtag extractor requires internal app signing keys that
are no longer available. This collector uses Playwright to scrape video URLs
directly from hashtag pages (like a real browser), then downloads with yt-dlp.

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
Dependencies: playwright, yt-dlp, subprocess, json
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

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


def _run_with_retry(cmd: list[str], retries: int = 3) -> subprocess.CompletedProcess:
    """Run a shell command with exponential-style retries."""
    last_exc: Optional[Exception] = None
    for attempt, delay in enumerate((_RETRY_DELAYS + [0])[:retries], start=1):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
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


def _playwright_available() -> bool:
    """Check whether playwright and its browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


class TikTokCollector(BaseCollector):
    """
    Collects TikTok videos using Playwright for URL discovery + yt-dlp for download.

    Falls back gracefully if Playwright is not installed — logs a clear warning
    and returns an empty list rather than crashing the pipeline.
    """

    PLATFORM = "tiktok"
    _HASHTAG_URL = "https://www.tiktok.com/tag/{tag}"

    def __init__(
        self,
        output_dir: str,
        max_results: int = 20,
        cookies_file: Optional[str] = None,
    ):
        """
        Initialize the TikTok collector.

        Args:
            output_dir: Directory for downloaded files.
            max_results: Maximum videos to collect per run.
            cookies_file: Path to a Netscape cookies.txt from a logged-in
                          TikTok session. Falls back to TIKTOK_COOKIES_FILE env var.
        """
        super().__init__(output_dir, max_results)
        self.cookies_file = cookies_file or os.environ.get("TIKTOK_COOKIES_FILE")
        if not _playwright_available():
            logger.warning(
                "Playwright not installed — TikTok collection disabled. "
                "Run: pip install playwright && playwright install chromium"
            )

    def _cookies_args(self) -> list[str]:
        """Return yt-dlp --cookies argument if a cookies file is available."""
        if self.cookies_file and os.path.exists(self.cookies_file):
            return ["--cookies", self.cookies_file]
        return []

    def search(self, queries: list[str], hours_back: int = 24) -> list[VideoMetadata]:
        """
        Scrape TikTok hashtag pages using Playwright to discover video URLs.

        Args:
            queries: Hashtag names or search terms.
            hours_back: Not used (TikTok doesn't expose timestamps in scrape).

        Returns:
            List of VideoMetadata objects with URLs ready for download.
        """
        if not _playwright_available():
            logger.warning("Playwright not available — skipping TikTok search.")
            return []

        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        seen_ids: set[str] = set()
        results: list[VideoMetadata] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_MOBILE_UA,
                viewport={"width": 390, "height": 844},
                locale="pt-BR",
            )

            # Load cookies if available
            if self.cookies_file and os.path.exists(self.cookies_file):
                _load_playwright_cookies(context, self.cookies_file)

            page = context.new_page()

            for query in queries[:10]:
                tag = query.lstrip("#").replace(" ", "").lower()
                url = self._HASHTAG_URL.format(tag=tag)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)  # let JS render

                    # Extract video links from the page
                    links = page.eval_on_selector_all(
                        "a[href*='/video/']",
                        "els => els.map(e => e.href)",
                    )

                    for link in links[:5]:
                        vid_id = _extract_tiktok_id(link)
                        if not vid_id or vid_id in seen_ids:
                            continue
                        seen_ids.add(vid_id)

                        # Try to get title from page
                        title = tag
                        try:
                            title = page.title() or tag
                        except Exception:
                            pass

                        results.append(
                            VideoMetadata(
                                video_id=vid_id,
                                title=title,
                                url=link,
                                platform=self.PLATFORM,
                                channel="",
                                published_at=None,
                                duration_seconds=0,
                                view_count=0,
                                like_count=0,
                                description="",
                                keywords_matched=[query],
                            )
                        )

                    logger.info("TikTok tag '%s': found %d links", tag, len(links))

                except PWTimeout:
                    logger.warning("Playwright timeout for TikTok tag '%s'", tag)
                except Exception as exc:
                    logger.warning("TikTok scrape error for tag '%s': %s", tag, exc)

                time.sleep(2)

            browser.close()

        logger.info("TikTok search found %d candidate videos", len(results))
        return results

    def _scrape_video_page(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Scrape a TikTok video page with Playwright to extract description text
        and capture a page screenshot — used when video download is blocked.

        Args:
            metadata: VideoMetadata with a valid TikTok URL.

        Returns:
            metadata updated with prefetched_transcript (description text)
            and thumbnail_paths (page screenshot).
        """
        if not _playwright_available():
            return metadata
        from playwright.sync_api import sync_playwright

        safe_id = metadata.video_id.replace("/", "_").replace("\\", "_")[:64]
        shot_path = os.path.join(self.output_dir, f"{self.PLATFORM}_{safe_id}_page.png")

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=_MOBILE_UA,
                    viewport={"width": 390, "height": 844},
                    locale="pt-BR",
                )
                if self.cookies_file and os.path.exists(self.cookies_file):
                    _load_playwright_cookies(context, self.cookies_file)
                page = context.new_page()
                page.goto(metadata.url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # Attempt to extract video description / caption text
                description = ""
                for selector in [
                    "[data-e2e='browse-video-desc']",
                    "[class*='DivVideoDesc']",
                    "meta[name='description']",
                ]:
                    try:
                        if selector.startswith("meta"):
                            description = page.get_attribute(selector, "content") or ""
                        else:
                            description = page.inner_text(selector) or ""
                        if description:
                            break
                    except Exception:
                        continue

                # Fallback: page title
                if not description:
                    try:
                        description = page.title()
                    except Exception:
                        pass

                page.screenshot(path=shot_path, full_page=False)
                browser.close()

            if description:
                metadata.prefetched_transcript = description
                logger.info("TikTok page text scraped for %s (%d chars)", metadata.video_id, len(description))
            if os.path.exists(shot_path):
                metadata.thumbnail_paths = [shot_path]
                logger.info("TikTok page screenshot saved: %s", shot_path)

        except Exception as exc:
            logger.warning("TikTok page scrape failed for %s: %s", metadata.video_id, exc)

        return metadata

    def download(self, metadata: VideoMetadata) -> VideoMetadata:
        """
        Attempt to download a TikTok video; fall back to page scraping.

        Primary path: yt-dlp video + ffmpeg audio extraction.
        Fallback (bot-detection / status code 0): Playwright page scrape for
        description text and a page screenshot.

        Args:
            metadata: VideoMetadata with a valid TikTok URL.

        Returns:
            Updated VideoMetadata. On success: local_path + audio_path set.
            On failure: prefetched_transcript + thumbnail_paths set instead.
        """
        safe_id = metadata.video_id.replace("/", "_").replace("\\", "_")[:64]
        out_template = os.path.join(
            self.output_dir, f"{self.PLATFORM}_{safe_id}.%(ext)s"
        )

        video_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--output", out_template,
            "--user-agent", _MOBILE_UA,
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
        except Exception as exc:
            logger.warning(
                "TikTok download failed for %s (%s) — using page scrape fallback.",
                metadata.video_id, exc,
            )
            metadata = self._scrape_video_page(metadata)

        return metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tiktok_id(url: str) -> Optional[str]:
    """Extract the numeric video ID from a TikTok video URL."""
    try:
        # URLs: https://www.tiktok.com/@user/video/7123456789012345678
        parts = url.rstrip("/").split("/")
        if "video" in parts:
            idx = parts.index("video")
            if idx + 1 < len(parts):
                vid_id = parts[idx + 1].split("?")[0]
                if vid_id.isdigit():
                    return vid_id
    except Exception:
        pass
    return None


def _load_playwright_cookies(context, cookies_txt_path: str) -> None:
    """
    Load Netscape-format cookies.txt into a Playwright browser context.

    Args:
        context: Playwright BrowserContext.
        cookies_txt_path: Path to cookies.txt file.
    """
    cookies = []
    try:
        with open(cookies_txt_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, _, path, secure, expires, name, value = parts[:7]
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": domain.lstrip("."),
                    "path": path,
                    "secure": secure.upper() == "TRUE",
                    "sameSite": "Lax",
                })
        if cookies:
            context.add_cookies(cookies)
            logger.debug("Loaded %d cookies into Playwright context", len(cookies))
    except Exception as exc:
        logger.warning("Could not load cookies into Playwright: %s", exc)


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
