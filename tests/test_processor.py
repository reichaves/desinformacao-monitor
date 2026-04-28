"""
Unit tests for the processor module.

Tests cover screenshot extraction path validation and content analysis
JSON parsing. Gemini API calls are mocked.

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.processor.screenshot_extractor import get_video_duration
from src.processor.visual_analyzer import VisualAnalysisResult, VisualAnalyzer
from src.processor.content_analyzer import ContentAnalyzer


class TestScreenshotExtractor(unittest.TestCase):
    """Tests for screenshot_extractor module."""

    def test_raises_on_missing_file(self):
        """extract_screenshots should raise FileNotFoundError for missing file."""
        from src.processor.screenshot_extractor import extract_screenshots
        with self.assertRaises(FileNotFoundError):
            extract_screenshots("/nonexistent/video.mp4", "/tmp")


class TestVisualAnalyzer(unittest.TestCase):
    """Tests for VisualAnalyzer with mocked Gemini calls."""

    @patch("src.processor.visual_analyzer.genai")
    def test_empty_frame_list_returns_empty_result(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        os.environ["GEMINI_API_KEY"] = "test_key"
        analyzer = VisualAnalyzer()
        result = analyzer.analyze_frames([])
        self.assertEqual(result.frames, [])
        self.assertEqual(result.disinformation_signals, [])

    @patch("src.processor.visual_analyzer.genai")
    def test_missing_env_key_raises(self, mock_genai):
        """VisualAnalyzer should raise EnvironmentError without API key."""
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        with self.assertRaises(EnvironmentError):
            VisualAnalyzer(api_key=None)


class TestContentAnalyzer(unittest.TestCase):
    """Tests for ContentAnalyzer JSON parsing."""

    @patch("src.processor.content_analyzer.genai")
    def test_analysis_populates_fields(self, mock_genai):
        """ContentAnalyzer should correctly parse a well-formed Gemini response."""
        import json

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "resumo": "Vídeo contém desinformação eleitoral.",
            "tipo_desinformacao": "eleitoral",
            "severidade": 4,
            "justificativa_severidade": "Alega fraude nas urnas sem evidências.",
            "alvo": "TSE",
            "afirmacoes_falsas": ["Urnas são hackeáveis", "Voto impresso é mais seguro"],
            "contra_narrativa": "TSE tem auditoria independente aprovada.",
            "palavras_chave_encontradas": ["#FraudeNasUrnas"],
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        os.environ["GEMINI_API_KEY"] = "test_key"
        analyzer = ContentAnalyzer()

        visual = VisualAnalysisResult()
        result = analyzer.analyze(
            video_id="test123",
            platform="youtube",
            title="Urnas são fraudadas!",
            url="https://youtube.com/watch?v=test123",
            channel="Canal X",
            transcript="As urnas são fraudadas e o TSE é corrupto.",
            visual_result=visual,
            keywords_matched=["#FraudeNasUrnas"],
        )

        self.assertEqual(result.severity, 4)
        self.assertEqual(result.disinformation_type, "eleitoral")
        self.assertEqual(result.target_journalist_or_institution, "TSE")
        self.assertIn("Urnas são hackeáveis", result.claims)

    @patch("src.processor.content_analyzer.genai")
    def test_missing_env_key_raises(self, _mock_genai):
        """ContentAnalyzer should raise EnvironmentError without API key."""
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        with self.assertRaises(EnvironmentError):
            ContentAnalyzer(api_key=None)


if __name__ == "__main__":
    unittest.main()
