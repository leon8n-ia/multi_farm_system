"""Backblaze B2 bridge for uploading farm outputs to cloud storage.

Uploads files to pre-configured Backblaze B2 buckets, one per farm type.
Files are made publicly accessible via signed URLs.

Bucket names (configured 2025-04):
    data_cleaning:     multifarm-data-cleaning
    auto_reports:      multifarm-auto-reports
    product_listing:   multifarm-product-listing
    monetized_content: multifarm-monetized-content
    react_nextjs:      multifarm-react-nextjs
    devops_cloud:      multifarm-devops-cloud
    mobile_dev:        multifarm-mobile-dev

Required env vars for live mode:
    B2_KEY_ID          — Backblaze application key ID
    B2_APPLICATION_KEY — Backblaze application key

Runs in simulation mode when credentials are absent or BACKBLAZE_ENABLED=false.
"""
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bucket names by farm type
B2_BUCKET_NAMES: dict[str, str] = {
    "data_cleaning": "multifarm-data-cleaning",
    "auto_reports": "multifarm-auto-reports",
    "product_listing": "multifarm-product-listing",
    "monetized_content": "multifarm-monetized-content",
    "react_nextjs": "multifarm-react-nextjs",
    "devops_cloud": "multifarm-devops-cloud",
    "mobile_dev": "multifarm-mobile-dev",
}

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2
_DEFAULT_URL_EXPIRATION = 3600  # 1 hour


class BackblazeBridge:
    """Upload files to Backblaze B2 buckets per farm type.

    Runs in **simulation mode** (no network calls) when:
      - BACKBLAZE_ENABLED env var is "false"
      - B2_KEY_ID or B2_APPLICATION_KEY env vars are absent

    Args:
        key_id: Backblaze application key ID; falls back to B2_KEY_ID env var.
        application_key: Backblaze application key; falls back to B2_APPLICATION_KEY env var.
    """

    def __init__(
        self,
        key_id: str | None = None,
        application_key: str | None = None,
    ) -> None:
        self._key_id = key_id or os.environ.get("B2_KEY_ID")
        self._application_key = application_key or os.environ.get("B2_APPLICATION_KEY")
        self._enabled = os.environ.get("BACKBLAZE_ENABLED", "true").lower() == "true"
        self._simulation = not (
            self._enabled and self._key_id and self._application_key
        )
        self._b2_api: Any = None
        self._buckets: dict[str, Any] = {}  # Cache for bucket objects

        if self._simulation:
            reason = (
                "BACKBLAZE_ENABLED=false"
                if not self._enabled
                else "credentials not configured"
            )
            logger.info("[Backblaze] Running in simulation mode (%s).", reason)
        else:
            logger.info("[Backblaze] Live mode active.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_api(self) -> Any:
        """Lazy-initialize and return the B2 API instance."""
        if self._b2_api is not None:
            return self._b2_api

        if self._simulation:
            return None

        try:
            from b2sdk.v2 import B2Api, InMemoryAccountInfo

            info = InMemoryAccountInfo()
            self._b2_api = B2Api(info)
            self._b2_api.authorize_account("production", self._key_id, self._application_key)
            logger.info("[Backblaze] API authorized successfully.")
            return self._b2_api
        except ImportError as exc:
            logger.error("[Backblaze] b2sdk not installed: %s", exc)
            self._simulation = True
            return None
        except Exception as exc:
            logger.error("[Backblaze] Failed to authorize: %s", exc)
            self._simulation = True
            return None

    def _get_bucket(self, farm_type: str) -> Any:
        """Get bucket object for farm type (cached)."""
        if farm_type in self._buckets:
            return self._buckets[farm_type]

        api = self._get_api()
        if not api:
            return None

        bucket_name = B2_BUCKET_NAMES.get(farm_type)
        if not bucket_name:
            logger.error("[Backblaze] Unknown farm_type: %s", farm_type)
            return None

        try:
            bucket = api.get_bucket_by_name(bucket_name)
            self._buckets[farm_type] = bucket
            logger.info("[Backblaze] Bucket loaded: %s", bucket_name)
            return bucket
        except Exception as exc:
            logger.error("[Backblaze] Failed to get bucket %s: %s", bucket_name, exc)
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
                    "[Backblaze] %s attempt %d/%d failed: %s",
                    operation_name,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY_SECONDS)

        logger.error(
            "[Backblaze] %s failed after %d attempts: %s",
            operation_name,
            _MAX_RETRIES,
            last_error,
        )
        return None

    def _sim_result(self, file_name: str, farm_type: str) -> dict:
        """Generate a simulated upload result."""
        fake_id = f"sim-{uuid.uuid4().hex[:12]}"
        bucket_name = B2_BUCKET_NAMES.get(farm_type, "unknown")
        return {
            "file_id": fake_id,
            "file_name": file_name,
            "farm_type": farm_type,
            "bucket": bucket_name,
            "download_url": f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}?sim=true",
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
        """Upload a file to the Backblaze B2 bucket for the given farm type.

        If a file with the same name already exists in the bucket, it will
        be overwritten (B2 handles this automatically).

        Args:
            farm_type: One of: data_cleaning, auto_reports, product_listing, etc.
            file_path: Local path to the file to upload.
            file_name: Name to use in B2 (defaults to original filename).

        Returns:
            dict with: file_id, file_name, farm_type, bucket, download_url, simulation
        """
        file_path = Path(file_path)
        file_name = file_name or file_path.name
        bucket_name = B2_BUCKET_NAMES.get(farm_type)

        if not bucket_name:
            logger.error("[Backblaze] Unknown farm_type: %s", farm_type)
            return {
                "file_id": None,
                "file_name": file_name,
                "farm_type": farm_type,
                "bucket": None,
                "download_url": None,
                "simulation": self._simulation,
                "error": f"Unknown farm_type: {farm_type}",
            }

        if self._simulation:
            logger.info(
                "[Backblaze] [SIM] upload_file: %s -> %s/%s",
                file_path,
                bucket_name,
                file_name,
            )
            return self._sim_result(file_name, farm_type)

        if not file_path.exists():
            logger.error("[Backblaze] File not found: %s", file_path)
            return {
                "file_id": None,
                "file_name": file_name,
                "farm_type": farm_type,
                "bucket": bucket_name,
                "download_url": None,
                "simulation": False,
                "error": f"File not found: {file_path}",
            }

        bucket = self._get_bucket(farm_type)
        if not bucket:
            logger.warning("[Backblaze] Bucket unavailable, falling back to simulation.")
            return self._sim_result(file_name, farm_type)

        def upload():
            uploaded_file = bucket.upload_local_file(
                local_file=str(file_path),
                file_name=file_name,
            )
            return uploaded_file

        result = self._retry_operation(upload, f"upload_file({file_name})")
        if not result:
            logger.warning("[Backblaze] Upload failed, falling back to simulation.")
            return self._sim_result(file_name, farm_type)

        file_id = result.id_
        # Construct friendly download URL
        download_url = f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}"

        logger.info(
            "[Backblaze] Uploaded %s to %s: id=%s",
            file_name,
            bucket_name,
            file_id,
        )

        return {
            "file_id": file_id,
            "file_name": file_name,
            "farm_type": farm_type,
            "bucket": bucket_name,
            "download_url": download_url,
            "simulation": False,
        }

    def get_download_url(
        self,
        farm_type: str,
        file_name: str,
        expiration_seconds: int = _DEFAULT_URL_EXPIRATION,
    ) -> str | None:
        """Generate a signed download URL for a file.

        Args:
            farm_type: Farm type to identify the bucket.
            file_name: Name of the file in the bucket.
            expiration_seconds: URL validity in seconds (default 1 hour).

        Returns:
            Signed download URL or None on error.
        """
        bucket_name = B2_BUCKET_NAMES.get(farm_type)
        if not bucket_name:
            logger.warning("[Backblaze] Unknown farm_type: %s", farm_type)
            return None

        if self._simulation:
            logger.info("[Backblaze] [SIM] get_download_url: %s/%s", bucket_name, file_name)
            return f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}?sim=true"

        bucket = self._get_bucket(farm_type)
        if not bucket:
            return None

        try:
            # Get authorization token for download
            auth_token = bucket.get_download_authorization(
                file_name_prefix=file_name,
                valid_duration_in_seconds=expiration_seconds,
            )
            download_url = f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}?Authorization={auth_token}"
            logger.info("[Backblaze] Generated signed URL for %s (expires in %ds)", file_name, expiration_seconds)
            return download_url
        except Exception as exc:
            logger.error("[Backblaze] Failed to generate download URL: %s", exc)
            return None

    def delete_file(self, farm_type: str, file_name: str) -> bool:
        """Delete a file from the Backblaze B2 bucket.

        Args:
            farm_type: Farm type to identify the bucket.
            file_name: Name of the file to delete.

        Returns:
            True if deleted successfully (or simulated), False on error.
        """
        bucket_name = B2_BUCKET_NAMES.get(farm_type)
        if not bucket_name:
            logger.warning("[Backblaze] Unknown farm_type: %s", farm_type)
            return False

        if self._simulation:
            logger.info("[Backblaze] [SIM] delete_file: %s/%s", bucket_name, file_name)
            return True

        bucket = self._get_bucket(farm_type)
        if not bucket:
            logger.warning("[Backblaze] Bucket unavailable for delete.")
            return False

        def delete():
            # Find the file version(s)
            file_versions = list(bucket.ls(file_name, latest_only=False))
            if not file_versions:
                logger.warning("[Backblaze] File not found: %s", file_name)
                return True  # Already gone

            # Delete all versions
            for file_version, _ in file_versions:
                bucket.delete_file_version(file_version.id_, file_version.file_name)
            return True

        result = self._retry_operation(delete, f"delete_file({file_name})")
        if result:
            logger.info("[Backblaze] Deleted file: %s/%s", bucket_name, file_name)
            return True

        return False

    def list_files(self, farm_type: str, max_results: int = 100) -> list[dict]:
        """List files in the Backblaze B2 bucket for the given farm type.

        Args:
            farm_type: Farm type to identify the bucket.
            max_results: Maximum number of files to return.

        Returns:
            List of dicts with: file_id, file_name, size, upload_timestamp
        """
        bucket_name = B2_BUCKET_NAMES.get(farm_type)
        if not bucket_name:
            logger.warning("[Backblaze] Unknown farm_type: %s", farm_type)
            return []

        if self._simulation:
            logger.info("[Backblaze] [SIM] list_files: %s", bucket_name)
            return []

        bucket = self._get_bucket(farm_type)
        if not bucket:
            return []

        try:
            files = []
            for file_version, _ in bucket.ls(latest_only=True):
                files.append({
                    "file_id": file_version.id_,
                    "file_name": file_version.file_name,
                    "size": file_version.size,
                    "upload_timestamp": file_version.upload_timestamp,
                })
                if len(files) >= max_results:
                    break
            return files
        except Exception as exc:
            logger.error("[Backblaze] Failed to list files: %s", exc)
            return []
