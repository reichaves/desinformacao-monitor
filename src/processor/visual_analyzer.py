"""
Visual analysis of video screenshots using Gemini vision (google-genai SDK).

Sends batches of screenshots to Gemini and extracts descriptions,
on-screen text (OCR), and presence of disinformation indicators.

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
Dependencies: google-genai, Pillow, io, os
"""

import io
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types
from PIL import Image

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
_MAX_FRAMES_PER_BATCH = 10  # Gemini context: send up to 10 frames at once
_MAX_IMAGE_SIDE = 512       # Resize frames to save tokens


@dataclass
class FrameAnalysis:
    """Analysis result for a single video frame."""

    frame_path: str
    frame_index: int
    timestamp_seconds: float
    description: str
    ocr_text: str
    disinformation_indicators: list[str] = field(default_factory=list)
    confidence_score: float = 0.0


@dataclass
class VisualAnalysisResult:
    """Aggregated visual analysis result for all frames of a video."""

    frames: list[FrameAnalysis] = field(default_factory=list)
    overall_summary: str = ""
    key_texts_on_screen: list[str] = field(default_factory=list)
    disinformation_signals: list[str] = field(default_factory=list)


_BATCH_PROMPT = """Você é um analista especializado em desinformação e conteúdo jornalístico.
Analise os frames de vídeo abaixo (capturados a cada 3 segundos) e para CADA frame responda:

1. DESCRIÇÃO: Descreva brevemente o que aparece na imagem (pessoas, cenário, textos, gráficos).
2. TEXTO_NA_TELA: Transcreva literalmente qualquer texto visível (legendas, títulos, banners, overlays).
3. INDICADORES: Liste sinais de desinformação ou ataques à imprensa/democracia (ex: alegações falsas, linguagem inflamatória, símbolos extremistas, fake news visuais).

Responda em JSON no formato:
[
  {
    "frame": 1,
    "descricao": "...",
    "texto_na_tela": "...",
    "indicadores": ["...", "..."]
  },
  ...
]

IMPORTANTE: Responda APENAS com o JSON válido. Não adicione markdown ou texto extra."""


class VisualAnalyzer:
    """
    Analyzes video frames for visual content and disinformation signals.

    Sends frames in batches to Gemini vision model, extracting descriptions,
    OCR text, and disinformation indicators from each frame.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        interval_seconds: int = 3,
    ):
        """
        Initialize the visual analyzer.

        Args:
            api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
            model: Gemini model ID supporting vision.
            interval_seconds: Frame interval used during extraction (for timestamp calc).
        """
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )
        self.client = genai.Client(api_key=key)
        self.model_name = model
        self.interval_seconds = interval_seconds
        logger.info("VisualAnalyzer initialized with model: %s", model)

    def analyze_frames(self, frame_paths: list[str]) -> VisualAnalysisResult:
        """
        Analyze a list of screenshot PNG files.

        Processes frames in batches. For each batch, sends images to Gemini
        vision and parses the structured JSON response.

        Args:
            frame_paths: Sorted list of absolute paths to PNG frames.

        Returns:
            VisualAnalysisResult with per-frame analyses and overall summary.
        """
        result = VisualAnalysisResult()
        if not frame_paths:
            return result

        # Process in batches
        for batch_start in range(0, len(frame_paths), _MAX_FRAMES_PER_BATCH):
            batch = frame_paths[batch_start : batch_start + _MAX_FRAMES_PER_BATCH]
            batch_results = self._analyze_batch(batch, batch_start)
            result.frames.extend(batch_results)

        # Aggregate signals and OCR texts
        for frame in result.frames:
            if frame.ocr_text.strip():
                result.key_texts_on_screen.append(
                    f"[{frame.timestamp_seconds:.0f}s] {frame.ocr_text.strip()}"
                )
            result.disinformation_signals.extend(frame.disinformation_indicators)

        # Deduplicate signals
        result.disinformation_signals = list(dict.fromkeys(result.disinformation_signals))
        result.overall_summary = self._build_summary(result)

        logger.info(
            "Visual analysis complete: %d frames, %d signals",
            len(result.frames),
            len(result.disinformation_signals),
        )
        return result

    def _analyze_batch(
        self, frame_paths: list[str], offset: int
    ) -> list[FrameAnalysis]:
        """
        Send a batch of frames to Gemini and parse the response.

        Args:
            frame_paths: Paths for this batch.
            offset: Index offset for timestamp calculation.

        Returns:
            List of FrameAnalysis objects.
        """
        # Build the multimodal request parts
        parts: list = []
        valid_paths: list[str] = []

        for path in frame_paths:
            img_bytes = _load_image_bytes(path)
            if img_bytes:
                parts.append(
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                )
                valid_paths.append(path)

        if not parts:
            return []

        parts.append(_BATCH_PROMPT)

        analyses: list[FrameAnalysis] = []
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=parts,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            raw = response.text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            parsed = json.loads(raw)
            for item in parsed:
                idx = item.get("frame", 1) - 1 + offset
                path = valid_paths[item.get("frame", 1) - 1] if valid_paths else ""
                analyses.append(
                    FrameAnalysis(
                        frame_path=path,
                        frame_index=idx,
                        timestamp_seconds=idx * self.interval_seconds,
                        description=item.get("descricao", ""),
                        ocr_text=item.get("texto_na_tela", ""),
                        disinformation_indicators=item.get("indicadores", []),
                    )
                )
        except Exception as exc:
            logger.error("Batch visual analysis failed: %s", exc, exc_info=True)
            # Return empty analysis for each frame in batch rather than crashing
            for i, path in enumerate(valid_paths):
                analyses.append(
                    FrameAnalysis(
                        frame_path=path,
                        frame_index=offset + i,
                        timestamp_seconds=(offset + i) * self.interval_seconds,
                        description="Análise indisponível",
                        ocr_text="",
                    )
                )

        return analyses

    def _build_summary(self, result: VisualAnalysisResult) -> str:
        """Build a plain-text summary of the visual analysis."""
        n_frames = len(result.frames)
        n_signals = len(result.disinformation_signals)
        texts_count = len(result.key_texts_on_screen)
        return (
            f"{n_frames} frames analisados | "
            f"{n_signals} sinais de desinformação detectados | "
            f"{texts_count} textos na tela identificados"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_image_bytes(path: str, max_side: int = _MAX_IMAGE_SIDE) -> Optional[bytes]:
    """
    Load an image, resize it to save tokens, and return PNG bytes.

    Args:
        path: Path to the PNG file.
        max_side: Maximum dimension for the longest side after resizing.

    Returns:
        PNG bytes, or None if loading fails.
    """
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as exc:
        logger.warning("Could not load image '%s': %s", path, exc)
        return None
