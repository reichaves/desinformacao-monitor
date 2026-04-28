"""
Google Drive uploader using OAuth 2.0 with a pre-obtained refresh token.

Files are uploaded as the authenticated user (personal Google account),
so storage quota is counted against the user — not a service account.

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: google-api-python-client, google-auth, google-auth-oauthlib
"""

import logging
import mimetypes
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DriveUploader:
    """
    Uploads pipeline outputs to Google Drive using OAuth 2.0.

    Authentication uses a refresh token (obtained via setup_drive_auth.py)
    stored as environment variables. Files are owned by the personal Google
    account, avoiding the service account quota limitation.

    Required environment variables:
        GOOGLE_DRIVE_CLIENT_ID      — OAuth 2.0 client ID
        GOOGLE_DRIVE_CLIENT_SECRET  — OAuth 2.0 client secret
        GOOGLE_DRIVE_REFRESH_TOKEN  — Refresh token from one-time auth flow
        GOOGLE_DRIVE_FOLDER_ID      — ID of the target Drive folder
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        folder_id: Optional[str] = None,
    ):
        """
        Initialize the Drive uploader with OAuth credentials.

        Args:
            client_id: OAuth client ID. Falls back to GOOGLE_DRIVE_CLIENT_ID.
            client_secret: OAuth client secret. Falls back to GOOGLE_DRIVE_CLIENT_SECRET.
            refresh_token: Refresh token. Falls back to GOOGLE_DRIVE_REFRESH_TOKEN.
            folder_id: Drive folder ID. Falls back to GOOGLE_DRIVE_FOLDER_ID.

        Raises:
            EnvironmentError: If any required variable is missing.
        """
        cid = client_id or os.environ.get("GOOGLE_DRIVE_CLIENT_ID")
        csecret = client_secret or os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET")
        rtoken = refresh_token or os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN")

        if not all([cid, csecret, rtoken]):
            raise EnvironmentError(
                "Google Drive OAuth credentials not found. "
                "Set GOOGLE_DRIVE_CLIENT_ID, GOOGLE_DRIVE_CLIENT_SECRET, "
                "and GOOGLE_DRIVE_REFRESH_TOKEN environment variables. "
                "Run 'python setup_drive_auth.py' to obtain them."
            )

        self.folder_id = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        if not self.folder_id:
            raise EnvironmentError(
                "Google Drive folder ID not found. Set GOOGLE_DRIVE_FOLDER_ID."
            )

        credentials = Credentials(
            token=None,
            refresh_token=rtoken,
            client_id=cid,
            client_secret=csecret,
            token_uri=_TOKEN_URI,
            scopes=_SCOPES,
        )
        # Force refresh to get a valid access token
        credentials.refresh(Request())

        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        logger.info("DriveUploader ready (OAuth). Target folder: %s", self.folder_id)

    def create_run_folder(self, run_name: str) -> str:
        """
        Create a dated subfolder inside the target Drive folder.

        Args:
            run_name: Name for the subfolder (e.g. '2026-04-28_070000').

        Returns:
            Drive folder ID of the new subfolder.
        """
        metadata = {
            "name": run_name,
            "mimeType": _FOLDER_MIME,
            "parents": [self.folder_id],
        }
        try:
            folder = self.service.files().create(body=metadata, fields="id").execute()
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
            drive_filename: Name on Drive (defaults to basename).
            parent_folder_id: Target folder ID (defaults to self.folder_id).

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
            logger.info("Uploaded '%s' → Drive id=%s", name, uploaded.get("id"))
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
        Upload all outputs from one pipeline run to a named subfolder on Drive.

        Args:
            summary_json_path: Path to run_summary.json.
            report_html_path: Path to the generated index.html.
            run_name: Label for the Drive subfolder.
            screenshot_paths: Optional list of screenshot PNG paths.

        Returns:
            Dict mapping file types to their Drive metadata dicts.
        """
        run_folder_id = self.create_run_folder(run_name)
        uploads: dict = {}

        if os.path.exists(summary_json_path):
            uploads["summary_json"] = self.upload_file(
                summary_json_path, "run_summary.json", run_folder_id
            )

        if os.path.exists(report_html_path):
            uploads["report_html"] = self.upload_file(
                report_html_path, "report.html", run_folder_id
            )

        if screenshot_paths:
            screenshots_folder_id = self._create_subfolder("screenshots", run_folder_id)
            for path in screenshot_paths[:50]:
                try:
                    self.upload_file(path, parent_folder_id=screenshots_folder_id)
                except Exception as exc:
                    logger.warning("Screenshot upload failed (%s): %s", path, exc)

        logger.info("Run '%s' uploaded to Drive: %d items", run_name, len(uploads))
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
