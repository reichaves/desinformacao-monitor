"""
Extract screenshots from video files at a fixed interval using ffmpeg.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: ffmpeg (system binary), subprocess, os
"""

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 3  # seconds between frames


def extract_screenshots(
    video_path: str,
    output_dir: str,
    interval_seconds: int = _DEFAULT_INTERVAL,
) -> list[str]:
    """
    Extract one screenshot every `interval_seconds` from a video file.

    Uses ffmpeg's `fps` video filter for accurate, evenly-spaced frames.
    Output images are PNG files named frame_NNNNNN.png.

    Args:
        video_path: Absolute path to the input video file.
        output_dir: Directory where PNG frames will be written.
        interval_seconds: Capture a frame every N seconds (default: 3).

    Returns:
        Sorted list of absolute paths to the extracted PNG files.

    Raises:
        FileNotFoundError: If the video file does not exist.
        RuntimeError: If ffmpeg exits with a non-zero status.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    os.makedirs(output_dir, exist_ok=True)

    out_pattern = os.path.join(output_dir, "frame_%06d.png")
    fps_value = f"1/{interval_seconds}"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"fps={fps_value}",
        "-vsync", "vfr",
        "-q:v", "2",
        out_pattern,
    ]

    logger.debug("Running: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exited {result.returncode}: {result.stderr[-400:]}"
            )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg timed out during screenshot extraction") from exc

    frames = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("frame_") and f.endswith(".png")
    )

    logger.info(
        "Extracted %d frames from '%s' (every %ds)",
        len(frames),
        os.path.basename(video_path),
        interval_seconds,
    )
    return frames


def get_video_duration(video_path: str) -> Optional[float]:
    """
    Return the video duration in seconds using ffprobe.

    Args:
        video_path: Path to the video file.

    Returns:
        Duration in seconds as a float, or None if unavailable.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("Could not read duration of '%s': %s", video_path, exc)
        return None
