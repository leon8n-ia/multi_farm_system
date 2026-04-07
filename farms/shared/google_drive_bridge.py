"""Google Drive bridge for uploading farm outputs to shared folders.

Uploads files to pre-configured Google Drive folders, one per farm type.
Each folder is publicly accessible via link for distribution.

Folder IDs (configured 2026-04):
    data_cleaning:     1qjVs8bQ6XzuSzuMin1fvR82wA-7NZza9
    auto_reports:      1tcd4KREz_ABMzORmg_a9s5BXvuZHsjxD
    product_listing:   1P7SCGJ0m8J-wLg678eZWkvYfcm5y5v7g
    monetized_content: 1GO03fu8aM0nXNYxNBOSFb4ESkWwgidcg

Required env vars for live mode:
    GOOGLE_DRIVE_CREDENTIALS_JSON — service account credentials (JSON string)
    GOOGLE_DRIVE_ENABLED          — set to "true" to enable (optional, defaults to true if creds present)

Runs in simulation mode when credentials are absent or GOOGLE_DRIVE_ENABLED=false.
"""
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Folder IDs by farm type
DRIVE_FOLDER_IDS: dict[str, str] = {
    "data_cleaning": "1qjVs8bQ6XzuSzuMin1fvR82wA-7NZza9",
    "auto_reports": "1tcd4KREz_ABMzORmg_a9s5BXvuZHsjxD",
    "product_listing": "1P7SCGJ0m8J-wLg678eZWkvYfcm5y5v7g",
    "monetized_content": "1GO03fu8aM0nXNYxNBOSFb4ESkWwgidcg",
    "react_nextjs": "19kIvsTU7O7ReSGrBOaAoBIkZ3OZmXXwL",
    "devops_cloud": "1A69s783nK31hGAqtjb8yoqoHKU-kG1Ic",
    "mobile_dev": "1o9Xx3yA2E6v_rcucaG14mIuXM_r-R9Ub",
}

# Public folder links
DRIVE_FOLDER_LINKS: dict[str, str] = {
    farm_type: f"https://drive.google.com/drive/folders/{folder_id}"
    for farm_type, folder_id in DRIVE_FOLDER_IDS.items()
}

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2


class GoogleDriveBridge:
    """Upload files to Google Drive folders per farm type.

    Runs in **simulation mode** (no network calls) when:
      - GOOGLE_DRIVE_ENABLED env var is "false"
      - GOOGLE_DRIVE_CREDENTIALS_JSON env var is absent or invalid

    Args:
        credentials_json: Service account credentials as JSON string;
                          falls back to GOOGLE_DRIVE_CREDENTIALS_JSON env var
                          or a local credentials file.
    """

    def __init__(self, credentials_json: str | None = None) -> None:
        self._credentials_json = credentials_json or os.environ.get(
            "GOOGLE_DRIVE_CREDENTIALS_JSON"
        )
        # Fallback: try to read from local credentials file
        if not self._credentials_json:
            # Try multiple paths for the credentials file
            possible_paths = [
                Path("multifarm-system-5452ce63eaef.json"),  # CWD
                Path(__file__).parent.parent.parent / "multifarm-system-5452ce63eaef.json",  # Relative to module
            ]
            for creds_file in possible_paths:
                if creds_file.exists():
                    try:
                        self._credentials_json = creds_file.read_text(encoding="utf-8")
                        logger.info("[GoogleDrive] Loaded credentials from %s", creds_file.resolve())
                        break
                    except Exception as exc:
                        logger.warning("[GoogleDrive] Failed to read %s: %s", creds_file, exc)
        self._enabled = os.environ.get("GOOGLE_DRIVE_ENABLED", "true").lower() == "true"
        self._simulation = not (self._enabled and self._credentials_json)
        self._service: Any = None

        if self._simulation:
            reason = (
                "GOOGLE_DRIVE_ENABLED=false"
                if not self._enabled
                else "credentials not configured"
            )
            logger.info("[GoogleDrive] Running in simulation mode (%s).", reason)
        else:
            logger.info("[GoogleDrive] Live mode active.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_service(self) -> Any:
        """Lazy-initialize and return the Google Drive API service."""
        if self._service is not None:
            return self._service

        if self._simulation:
            return None

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = json.loads(self._credentials_json)  # type: ignore
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            self._service = build("drive", "v3", credentials=credentials)
            logger.info("[GoogleDrive] Service initialized successfully.")
            return self._service
        except ImportError as exc:
            logger.error(
                "[GoogleDrive] google-api-python-client not installed: %s", exc
            )
            self._simulation = True
            return None
        except json.JSONDecodeError as exc:
            logger.error("[GoogleDrive] Invalid credentials JSON: %s", exc)
            self._simulation = True
            return None
        except Exception as exc:
            logger.error("[GoogleDrive] Failed to initialize service: %s", exc)
            self._simulation = True
            return None

    def _retry_operation(self, operation: callable, operation_name: str) -> Any:
        """Execute operation with retry logic."""
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[GoogleDrive] %s attempt %d/%d failed: %s",
                    operation_name,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_SECONDS)

        logger.error(
            "[GoogleDrive] %s failed after %d attempts: %s",
            operation_name,
            _MAX_RETRIES,
            last_error,
        )
        return None

    def _find_existing_file(self, folder_id: str, file_name: str) -> str | None:
        """Find existing file by name in folder, return file_id or None."""
        service = self._get_service()
        if not service:
            return None

        def search():
            query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
            response = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            files = response.get("files", [])
            return files[0]["id"] if files else None

        return self._retry_operation(search, f"find_file({file_name})")

    def _sim_result(self, file_name: str, farm_type: str) -> dict:
        """Generate a simulated upload result."""
        fake_id = f"sim-{uuid.uuid4().hex[:12]}"
        return {
            "file_id": fake_id,
            "file_name": file_name,
            "folder_id": DRIVE_FOLDER_IDS.get(farm_type, "unknown"),
            "web_view_link": f"https://drive.google.com/file/d/{fake_id}/view",
            "simulation": True,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_file(
        self,
        farm_type: str,
        file_path: str | Path,
        file_name: str | None = None,
    ) -> dict:
        """Upload a file to the Google Drive folder for the given farm type.

        If a file with the same name already exists in the folder, it is
        deleted before uploading the new version.

        Args:
            farm_type: One of: data_cleaning, auto_reports, product_listing, monetized_content
            file_path: Local path to the file to upload
            file_name: Name to use in Drive (defaults to original filename)

        Returns:
            dict with: file_id, file_name, folder_id, web_view_link, simulation
        """
        file_path = Path(file_path)
        file_name = file_name or file_path.name
        folder_id = DRIVE_FOLDER_IDS.get(farm_type)

        if not folder_id:
            logger.error("[GoogleDrive] Unknown farm_type: %s", farm_type)
            return {
                "file_id": None,
                "file_name": file_name,
                "folder_id": None,
                "web_view_link": None,
                "simulation": self._simulation,
                "error": f"Unknown farm_type: {farm_type}",
            }

        if self._simulation:
            logger.info(
                "[GoogleDrive] [SIM] upload_file: %s -> %s/%s",
                file_path,
                farm_type,
                file_name,
            )
            return self._sim_result(file_name, farm_type)

        if not file_path.exists():
            logger.error("[GoogleDrive] File not found: %s", file_path)
            return {
                "file_id": None,
                "file_name": file_name,
                "folder_id": folder_id,
                "web_view_link": None,
                "simulation": False,
                "error": f"File not found: {file_path}",
            }

        service = self._get_service()
        if not service:
            logger.warning("[GoogleDrive] Service unavailable, falling back to simulation.")
            return self._sim_result(file_name, farm_type)

        # Delete existing file with same name
        existing_id = self._find_existing_file(folder_id, file_name)
        if existing_id:
            logger.info("[GoogleDrive] Deleting existing file: %s", existing_id)
            self.delete_file(existing_id)

        # Upload new file
        def upload():
            from googleapiclient.http import MediaFileUpload

            file_metadata = {
                "name": file_name,
                "parents": [folder_id],
            }
            media = MediaFileUpload(str(file_path), resumable=True)
            uploaded = (
                service.files()
                .create(body=file_metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
            return uploaded

        result = self._retry_operation(upload, f"upload_file({file_name})")
        if not result:
            logger.warning("[GoogleDrive] Upload failed, falling back to simulation.")
            return self._sim_result(file_name, farm_type)

        file_id = result.get("id")
        web_link = result.get("webViewLink")
        logger.info(
            "[GoogleDrive] Uploaded %s to %s: id=%s",
            file_name,
            farm_type,
            file_id,
        )

        return {
            "file_id": file_id,
            "file_name": file_name,
            "folder_id": folder_id,
            "web_view_link": web_link,
            "simulation": False,
        }

    def get_folder_link(self, farm_type: str) -> str | None:
        """Return the public link to the Google Drive folder for the farm type.

        Args:
            farm_type: One of: data_cleaning, auto_reports, product_listing, monetized_content

        Returns:
            Public folder URL or None if farm_type is unknown.
        """
        link = DRIVE_FOLDER_LINKS.get(farm_type)
        if not link:
            logger.warning("[GoogleDrive] Unknown farm_type: %s", farm_type)
        return link

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive by its file ID.

        Args:
            file_id: The Google Drive file ID to delete.

        Returns:
            True if deleted successfully (or simulated), False on error.
        """
        if self._simulation:
            logger.info("[GoogleDrive] [SIM] delete_file: %s", file_id)
            return True

        service = self._get_service()
        if not service:
            logger.warning("[GoogleDrive] Service unavailable for delete.")
            return False

        def delete():
            service.files().delete(fileId=file_id).execute()
            return True

        result = self._retry_operation(delete, f"delete_file({file_id})")
        if result:
            logger.info("[GoogleDrive] Deleted file: %s", file_id)
            return True

        return False

    def list_files(self, farm_type: str, max_results: int = 100) -> list[dict]:
        """List files in the Google Drive folder for the given farm type.

        Args:
            farm_type: One of: data_cleaning, auto_reports, product_listing, monetized_content
            max_results: Maximum number of files to return.

        Returns:
            List of dicts with: id, name, mimeType, webViewLink
        """
        folder_id = DRIVE_FOLDER_IDS.get(farm_type)
        if not folder_id:
            logger.warning("[GoogleDrive] Unknown farm_type: %s", farm_type)
            return []

        if self._simulation:
            logger.info("[GoogleDrive] [SIM] list_files: %s", farm_type)
            return []

        service = self._get_service()
        if not service:
            return []

        def list_op():
            query = f"'{folder_id}' in parents and trashed=false"
            response = (
                service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name, mimeType, webViewLink)",
                    pageSize=max_results,
                )
                .execute()
            )
            return response.get("files", [])

        result = self._retry_operation(list_op, f"list_files({farm_type})")
        return result or []
