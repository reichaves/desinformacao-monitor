"""
Google Drive uploader using a service account for automated (headless) access.

Uploads run results (JSON summaries, screenshots, HTML report) to a
designated folder in Google Drive and returns shareable file links.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: google-api-python-client, google-auth, os, json, base64
"""

import base64
import json
import logging
import mimetypes
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveUploader:
    """
    Uploads pipeline outputs to Google Drive using a service account.

    Authentication uses a service account JSON key stored as an environment
    variable (base64-encoded). Never hardcode credentials.

    Required environment variables:
        GOOGLE_DRIVE_CREDENTIALS_B64  - base64-encoded service account JSON
        GOOGLE_DRIVE_FOLDER_ID        - ID of the target Drive folder
    """

    def __init__(
        self,
        credentials_b64: Optional[str] = None,
        folder_id: Optional[str] = None,
    ):
        """
        Initialize the Drive uploader.

        Args:
            credentials_b64: Base64-encoded service account JSON.
                             Falls back to GOOGLE_DRIVE_CREDENTIALS_B64 env var.
            folder_id: Drive folder ID to upload into.
                       Falls back to GOOGLE_DRIVE_FOLDER_ID env var.

        Raises:
            EnvironmentError: If credentials or folder_id are not available.
        """
        creds_b64 = credentials_b64 or os.environ.get("GOOGLE_DRIVE_CREDENTIALS_B64")
        if not creds_b64:
            raise EnvironmentError(
                "Google Drive credentials not found. "
                "Set GOOGLE_DRIVE_CREDENTIALS_B64 environment variable."
            )

        self.folder_id = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        if not self.folder_id:
            raise EnvironmentError(
                "Google Drive folder ID not found. "
                "Set GOOGLE_DRIVE_FOLDER_ID environment variable."
            )

        # Decode base64 JSON and build credentials
        creds_json = base64.b64decode(creds_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=_SCOPES
        )
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        logger.info("DriveUploader ready. Target folder: %s", self.folder_id)

    def create_run_folder(self, run_name: str) -> str:
        """
        Create a subdirectory in the target Drive folder for this run.

        Args:
            run_name: Name for the new subfolder (e.g. '2026-04-28_070000').

        Returns:
            Drive folder ID of the newly created subfolder.
        """
        metadata = {
            "name": run_name,
            "mimeType": _FOLDER_MIME,
            "parents": [self.folder_id],
        }
        try:
            folder = (
                self.service.files()
                .create(body=metadata, fields="id")
                .execute()
            )
            folder_id = folder["id"]
            logger.info("Created Drive subfolder '%s' (id=%s)", run_name, folder_id)
            return folder_id
        except HttpError as exc:
            logger.error("Failed to create Drive subfolder: %s", exc)
            raise

    def upload_file(
        self,
        local_path: str,
        drive_filename: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
    ) -> dict:
        """
        Upload a single local file to Google Drive.

        Args:
            local_path: Absolute path to the local file.
            drive_filename: Name to use on Drive (defaults to basename).
            parent_folder_id: Drive folder ID. Defaults to self.folder_id.

        Returns:
            Dict with 'id' and 'webViewLink' of the uploaded file.

        Raises:
            FileNotFoundError: If local_path does not exist.
            HttpError: On Drive API errors.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"File not found: {local_path}")

        name = drive_filename or os.path.basename(local_path)
        parent = parent_folder_id or self.folder_id
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"

        file_metadata = {"name": name, "parents": [parent]}
        media = MediaFileUpload(local_path, mimetype=mime, resumable=True)

        try:
            uploaded = (
                self.service.files()
                .create(body=file_metadata, media_body=media, fields="id,webViewLink")
                .execute()
            )
            logger.info(
                "Uploaded '%s' → Drive id=%s", name, uploaded.get("id")
            )
            return uploaded
        except HttpError as exc:
            logger.error("Drive upload failed for '%s': %s", local_path, exc)
            raise

    def upload_run_results(
        self,
        summary_json_path: str,
        report_html_path: str,
        run_name: str,
        screenshot_paths: Optional[list[str]] = None,
    ) -> dict:
        """
        Upload all outputs from one pipeline run to Drive.

        Creates a named subfolder and uploads JSON summary, HTML report,
        and optionally screenshots.

        Args:
            summary_json_path: Path to the run_summary.json file.
            report_html_path: Path to the generated index.html report.
            run_name: Label for the Drive subfolder (e.g. the run timestamp).
            screenshot_paths: Optional list of screenshot PNG paths to upload.

        Returns:
            Dict mapping file types to their Drive metadata dicts.
        """
        run_folder_id = self.create_run_folder(run_name)
        uploads: dict = {}

        # Upload JSON summary
        if os.path.exists(summary_json_path):
            uploads["summary_json"] = self.upload_file(
                summary_json_path, "run_summary.json", run_folder_id
            )

        # Upload HTML report
        if os.path.exists(report_html_path):
            uploads["report_html"] = self.upload_file(
                report_html_path, "report.html", run_folder_id
            )

        # Upload screenshots (limited to avoid hitting Drive quota)
        if screenshot_paths:
            screenshots_folder_id = self._create_subfolder("screenshots", run_folder_id)
            for path in screenshot_paths[:50]:  # cap at 50 screenshots per run
                try:
                    self.upload_file(path, parent_folder_id=screenshots_folder_id)
                except Exception as exc:
                    logger.warning("Screenshot upload failed (%s): %s", path, exc)

        logger.info(
            "Run '%s' uploaded to Drive: %d items", run_name, len(uploads)
        )
        return uploads

    def _create_subfolder(self, name: str, parent_id: str) -> str:
        """Create a nested subfolder and return its ID."""
        metadata = {
            "name": name,
            "mimeType": _FOLDER_MIME,
            "parents": [parent_id],
        }
        folder = self.service.files().create(body=metadata, fields="id").execute()
        return folder["id"]
