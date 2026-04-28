"""
Main pipeline orchestrator for the disinformation monitoring system.

Coordinates: collection → screenshots → transcription → visual analysis
             → content analysis → local storage → Drive upload → HTML report.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: See requirements.txt
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from src.collector.youtube_collector import YouTubeCollector
from src.collector.tiktok_collector import TikTokCollector
from src.processor.audio_transcriber import AudioTranscriber
from src.processor.content_analyzer import ContentAnalyzer
from src.processor.screenshot_extractor import extract_screenshots
from src.processor.visual_analyzer import VisualAnalyzer, VisualAnalysisResult
from src.reporter.html_generator import HtmlGenerator
from src.storage.drive_uploader import DriveUploader
from src.storage.local_storage import LocalStorage

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------

def _get_config() -> dict:
    """
    Load pipeline configuration from environment variables.

    Returns:
        Dict with all configuration values.

    Raises:
        SystemExit: If required variables are missing.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        logger.critical("GEMINI_API_KEY is not set. Aborting.")
        sys.exit(1)

    return {
        "gemini_api_key": gemini_key,
        "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20"),
        "max_videos": int(os.environ.get("MAX_VIDEOS_PER_RUN", "20")),
        "data_dir": os.environ.get("DATA_DIR", "data"),
        "docs_dir": os.environ.get("DOCS_DIR", "docs"),
        "keywords_path": os.environ.get("KEYWORDS_PATH", "config/keywords.json"),
        "screenshot_interval": int(os.environ.get("SCREENSHOT_INTERVAL_SECONDS", "3")),
        "enable_drive": os.environ.get("ENABLE_GOOGLE_DRIVE", "false").lower() == "true",
        "drive_credentials_b64": os.environ.get("GOOGLE_DRIVE_CREDENTIALS_B64"),
        "drive_folder_id": os.environ.get("GOOGLE_DRIVE_FOLDER_ID"),
        "hours_back": int(os.environ.get("HOURS_BACK", "24")),
    }


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def _load_keywords(path: str) -> tuple[list[str], list[str]]:
    """
    Load search queries for YouTube and TikTok from keywords.json.

    Args:
        path: Path to the keywords configuration file.

    Returns:
        Tuple of (youtube_queries, tiktok_queries).
    """
    with open(path, encoding="utf-8") as f:
        kw = json.load(f)
    yt_queries = kw.get("search_queries_youtube", [])
    tt_queries = kw.get("search_queries_tiktok", [])
    hashtags = kw.get("hashtags", [])
    terms = kw.get("terms", [])
    # Add a sample of hashtags/terms to queries
    yt_queries = yt_queries + hashtags[:5] + terms[:5]
    tt_queries = tt_queries + hashtags[:5]
    return yt_queries, tt_queries


def run_pipeline() -> None:
    """
    Execute the full disinformation monitoring pipeline for one daily run.

    Steps:
        1. Load configuration and keywords.
        2. Collect videos from YouTube and TikTok (up to max_videos total).
        3. For each video:
           a. Extract screenshots (every N seconds).
           b. Transcribe audio with Gemini.
           c. Analyse screenshots with Gemini vision.
           d. Run full content analysis with Gemini.
           e. Save analysis JSON.
        4. Generate and save run summary.
        5. Render interactive HTML report (→ docs/index.html).
        6. (Optional) Upload results to Google Drive.
        7. Clean up downloaded video files to save disk space.
    """
    config = _get_config()
    logger.info("=== Disinformation Monitor Pipeline START ===")
    logger.info("Config: max_videos=%d, hours_back=%dh, model=%s",
                config["max_videos"], config["hours_back"], config["gemini_model"])

    # --- Storage ---
    storage = LocalStorage(base_dir=config["data_dir"])

    # --- Keywords ---
    yt_queries, tt_queries = _load_keywords(config["keywords_path"])
    logger.info("Loaded %d YouTube queries, %d TikTok queries", len(yt_queries), len(tt_queries))

    # --- Collectors ---
    max_per_platform = max(1, config["max_videos"] // 2)
    yt_collector = YouTubeCollector(output_dir=storage.videos_dir, max_results=max_per_platform)
    tt_collector = TikTokCollector(output_dir=storage.videos_dir, max_results=max_per_platform)

    # --- Processors ---
    transcriber = AudioTranscriber(
        api_key=config["gemini_api_key"],
        model=config["gemini_model"],
    )
    visual_analyzer = VisualAnalyzer(
        api_key=config["gemini_api_key"],
        model=config["gemini_model"],
        interval_seconds=config["screenshot_interval"],
    )
    content_analyzer = ContentAnalyzer(
        api_key=config["gemini_api_key"],
        model=config["gemini_model"],
    )

    # --- Collect ---
    logger.info("Step 1/5: Collecting videos…")
    yt_videos = yt_collector.collect(yt_queries, hours_back=config["hours_back"])
    tt_videos = tt_collector.collect(tt_queries, hours_back=config["hours_back"])
    all_videos = yt_videos + tt_videos
    logger.info("Collected: %d YouTube + %d TikTok = %d total",
                len(yt_videos), len(tt_videos), len(all_videos))

    # --- Process each video ---
    all_screenshots: list[str] = []
    analyses: list[dict] = []

    logger.info("Step 2-4/5: Processing %d videos…", len(all_videos))
    for idx, video in enumerate(all_videos, start=1):
        logger.info("--- Video %d/%d: %s [%s] ---", idx, len(all_videos), video.video_id, video.platform)

        # Screenshots
        frame_paths: list[str] = []
        if video.local_path and os.path.exists(video.local_path):
            try:
                ss_dir = storage.screenshots_subdir(video.video_id)
                frame_paths = extract_screenshots(
                    video.local_path,
                    ss_dir,
                    interval_seconds=config["screenshot_interval"],
                )
                all_screenshots.extend(frame_paths[:5])  # Upload top 5 per video
            except Exception as exc:
                logger.warning("Screenshot extraction failed for %s: %s", video.video_id, exc)
        else:
            logger.warning("No local video file for %s — skipping screenshots", video.video_id)

        # Transcription
        transcript = ""
        if video.audio_path and os.path.exists(video.audio_path):
            try:
                transcript = transcriber.transcribe(video.audio_path)
            except Exception as exc:
                logger.warning("Transcription failed for %s: %s", video.video_id, exc)
        else:
            logger.warning("No audio file for %s — skipping transcription", video.video_id)

        # Visual analysis
        visual_result = VisualAnalysisResult()
        if frame_paths:
            try:
                visual_result = visual_analyzer.analyze_frames(frame_paths)
            except Exception as exc:
                logger.warning("Visual analysis failed for %s: %s", video.video_id, exc)

        # Content analysis
        try:
            analysis = content_analyzer.analyze(
                video_id=video.video_id,
                platform=video.platform,
                title=video.title,
                url=video.url,
                channel=video.channel,
                transcript=transcript,
                visual_result=visual_result,
                keywords_matched=video.keywords_matched,
                view_count=video.view_count,
                like_count=video.like_count,
                duration_seconds=video.duration_seconds,
                published_at=video.published_at.isoformat() if video.published_at else None,
            )
            analysis_dict = analysis.to_dict()
        except Exception as exc:
            logger.error("Content analysis failed for %s: %s", video.video_id, exc, exc_info=True)
            analysis_dict = {
                "video_id": video.video_id,
                "platform": video.platform,
                "title": video.title,
                "url": video.url,
                "channel": video.channel,
                "summary_pt": "Erro na análise automática.",
                "severity": 0,
                "disinformation_type": "outro",
                "claims": [],
                "keywords_found": video.keywords_matched,
                "view_count": video.view_count,
                "like_count": video.like_count,
                "duration_seconds": video.duration_seconds,
            }

        storage.save_analysis(analysis_dict)
        analyses.append(analysis_dict)
        logger.info("✓ Analysis saved for %s (severity=%s)", video.video_id, analysis_dict.get("severity"))

    # --- Summary ---
    logger.info("Step 5/5: Generating report…")
    summary_path = storage.save_run_summary(analyses)

    # --- HTML Report ---
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = os.path.join(config["docs_dir"], "index.html")
    generator = HtmlGenerator()
    generator.generate_from_file(summary_path, report_path)
    logger.info("HTML report: %s", report_path)

    # Also save a dated archive copy
    archive_path = os.path.join(config["docs_dir"], f"report_{run_date}.html")
    generator.generate_from_file(summary_path, archive_path)

    # --- Google Drive upload (optional) ---
    if config["enable_drive"]:
        logger.info("Uploading results to Google Drive…")
        try:
            uploader = DriveUploader(
                credentials_b64=config["drive_credentials_b64"],
                folder_id=config["drive_folder_id"],
            )
            run_name = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
            uploader.upload_run_results(
                summary_json_path=summary_path,
                report_html_path=report_path,
                run_name=run_name,
                screenshot_paths=all_screenshots[:30],
            )
            logger.info("Drive upload complete.")
        except Exception as exc:
            logger.error("Drive upload failed: %s", exc, exc_info=True)
    else:
        logger.info("Google Drive upload disabled. Set ENABLE_GOOGLE_DRIVE=true to enable.")

    # --- Cleanup ---
    storage.cleanup_videos()

    logger.info("=== Pipeline COMPLETE: %d videos analysed ===", len(analyses))


if __name__ == "__main__":
    run_pipeline()
