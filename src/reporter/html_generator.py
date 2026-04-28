"""
Interactive HTML report generator for GitHub Pages.

Reads the run_summary.json and renders a fully self-contained HTML page
using Chart.js + Tailwind CDN (zero-build, no Node.js required).

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
Dependencies: jinja2, json, os
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_TEMPLATE_NAME = "index_template.html"


class HtmlGenerator:
    """
    Generates an interactive GitHub Pages report from pipeline results.

    Uses Jinja2 to render a template with embedded Chart.js visualisations
    and a searchable table of all analysed videos.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize the HTML generator.

        Args:
            template_dir: Directory containing Jinja2 templates.
                          Defaults to the bundled templates/ directory.
        """
        tdir = template_dir or _TEMPLATE_DIR
        self.env = Environment(
            loader=FileSystemLoader(tdir),
            autoescape=True,
        )
        logger.info("HtmlGenerator initialized, templates: %s", tdir)

    def generate(self, summary: dict, output_path: str) -> str:
        """
        Render the interactive HTML report.

        Args:
            summary: Parsed run_summary.json dict with a 'videos' list.
            output_path: Absolute path where the HTML file will be written.

        Returns:
            Absolute path to the rendered HTML file.
        """
        videos = summary.get("videos", [])
        collected_at = summary.get("collected_at_utc", datetime.utcnow().isoformat() + "Z")
        total = len(videos)

        # --- Build chart data ---
        severity_counts = {str(i): 0 for i in range(6)}  # 0–5
        type_counts: dict[str, int] = {}
        platform_counts: dict[str, int] = {}

        high_severity = []
        for v in videos:
            sev = str(v.get("severity", 0))
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            dtype = v.get("disinformation_type", "outro")
            type_counts[dtype] = type_counts.get(dtype, 0) + 1

            plat = v.get("platform", "outro")
            platform_counts[plat] = platform_counts.get(plat, 0) + 1

            if v.get("severity", 0) >= 3:
                high_severity.append(v)

        template = self.env.get_template(_TEMPLATE_NAME)
        html = template.render(
            collected_at=collected_at,
            total_videos=total,
            high_severity_count=len(high_severity),
            videos=videos,
            high_severity=high_severity[:10],
            severity_counts_json=json.dumps(severity_counts),
            type_counts_json=json.dumps(type_counts),
            platform_counts_json=json.dumps(platform_counts),
            all_videos_json=json.dumps(videos, ensure_ascii=False),
        )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("HTML report written to: %s (%d videos)", output_path, total)
        return output_path

    def generate_from_file(self, summary_json_path: str, output_path: str) -> str:
        """
        Convenience wrapper: load summary from file, then generate.

        Args:
            summary_json_path: Path to run_summary.json.
            output_path: Path to write the HTML report.

        Returns:
            Absolute path to the rendered HTML file.
        """
        if not os.path.exists(summary_json_path):
            raise FileNotFoundError(f"Summary not found: {summary_json_path}")
        with open(summary_json_path, encoding="utf-8") as f:
            summary = json.load(f)
        return self.generate(summary, output_path)
