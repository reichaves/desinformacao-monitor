"""
Audio transcription using the Gemini File API (google-genai SDK).

Uploads MP3/WAV files to Gemini and requests a Portuguese transcription
with speaker diarization hints.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: google-genai, os, time
"""

import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"
_TRANSCRIPTION_PROMPT = (
    "Você é um transcritor profissional de áudio em português brasileiro. "
    "Transcreva TODO o áudio deste arquivo, palavra por palavra, com precisão máxima. "
    "Se houver múltiplos falantes, indique trocas de locutor com [Locutor 1], [Locutor 2], etc. "
    "Não resuma nem omita nenhuma palavra. "
    "Se o áudio for inaudível em algum trecho, escreva [inaudível]. "
    "Retorne APENAS a transcrição, sem comentários adicionais."
)


class AudioTranscriber:
    """
    Transcribes audio files using Gemini's multimodal capability.

    Uses the Gemini File API to upload audio and then requests a full
    word-for-word transcription in Brazilian Portuguese.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ):
        """
        Initialize the transcriber.

        Args:
            api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
            model: Gemini model ID to use for transcription.
        """
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )
        self.client = genai.Client(api_key=key)
        self.model_name = model
        logger.info("AudioTranscriber initialized with model: %s", model)

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe all speech from an audio file.

        Uploads the file to the Gemini File API, waits for processing,
        sends a transcription prompt, and returns the full transcript.

        Args:
            audio_path: Absolute path to the audio file (MP3 or WAV).

        Returns:
            Full transcript as a string. Returns an empty string on failure.

        Raises:
            FileNotFoundError: If the audio file does not exist.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        mime_type = mimetypes.guess_type(audio_path)[0] or "audio/mpeg"
        file_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
        logger.info(
            "Uploading audio '%s' (%.1f MB) to Gemini File API…",
            os.path.basename(audio_path),
            file_size_mb,
        )

        uploaded_file = None
        try:
            uploaded_file = self.client.files.upload(
                file=audio_path,
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=os.path.basename(audio_path),
                ),
            )

            # Wait until processing is complete (state = ACTIVE)
            uploaded_file = self._wait_for_active(uploaded_file)

            logger.info("Audio uploaded and active. Requesting transcription…")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[uploaded_file, _TRANSCRIPTION_PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=8192,
                ),
            )
            transcript = response.text.strip()
            logger.info(
                "Transcription complete: %d characters for '%s'",
                len(transcript),
                os.path.basename(audio_path),
            )
            return transcript

        except Exception as exc:
            logger.error(
                "Transcription failed for '%s': %s", audio_path, exc, exc_info=True
            )
            return ""

        finally:
            # Clean up uploaded file from Gemini servers
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    logger.debug("Deleted Gemini file: %s", uploaded_file.name)
                except Exception as del_exc:
                    logger.warning("Could not delete Gemini file: %s", del_exc)

    def _wait_for_active(self, file_obj, max_wait: int = 120) -> object:
        """
        Poll until the uploaded file transitions to ACTIVE state.

        Args:
            file_obj: Gemini File object returned by files.upload().
            max_wait: Maximum seconds to wait (default 120).

        Returns:
            Updated File object in ACTIVE state.

        Raises:
            TimeoutError: If the file is not active within max_wait seconds.
            RuntimeError: If the file enters a FAILED state.
        """
        elapsed = 0
        poll_interval = 3
        while elapsed < max_wait:
            updated = self.client.files.get(name=file_obj.name)
            state = str(updated.state)
            if "ACTIVE" in state:
                return updated
            if "FAILED" in state:
                raise RuntimeError(f"Gemini file processing FAILED: {file_obj.name}")
            logger.debug("File state: %s — waiting %ds…", state, poll_interval)
            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Gemini file '{file_obj.name}' not ACTIVE after {max_wait}s"
        )
