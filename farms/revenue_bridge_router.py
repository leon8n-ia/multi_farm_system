"""Revenue bridge router — fan-out to multiple bridges.

Routes publish_product, check_sales, record_sale_attempt and
get_market_feedback to all registered bridges.

Additionally supports BackblazeBridge for file uploads as a
secondary distribution channel.

Bridge activation is controlled by config flags:
  - LemonSqueezyRevenueBridge: config.LEMONSQUEEZY_ENABLED (PERMANENTLY DISABLED)
  - GumroadRevenueBridge: config.GUMROAD_ENABLED
  - BackblazeBridge: config.BACKBLAZE_ENABLED

All exceptions from individual bridge calls are caught and logged so
a broken bridge never interrupts the simulation cycle.
"""
import logging
from pathlib import Path

import config
from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge
from farms.gumroad_bridge import GumroadRevenueBridge
from farms.shared.backblaze_bridge import BackblazeBridge

logger = logging.getLogger(__name__)


class RevenueBridgeRouter:
    """Fan-out router for multiple revenue bridges.

    Args:
        bridges: Ordered list of bridge instances.  Activation is controlled
                 by config flags (LEMONSQUEEZY_ENABLED, GUMROAD_ENABLED).
                 LemonSqueezy is permanently disabled.
        farm_type: Farm type for Backblaze bucket routing (optional).
    """

    def __init__(self, bridges: list, farm_type: str | None = None) -> None:
        self._bridges = bridges
        self._attempts: list[dict] = []
        self._farm_type = farm_type
        self._storage_bridge: BackblazeBridge | None = None

        # Initialize Backblaze bridge if enabled and farm_type provided
        if farm_type and config.BACKBLAZE_ENABLED:
            self._storage_bridge = BackblazeBridge()
            logger.info("[Router] BackblazeBridge enabled for farm_type=%s", farm_type)

    def _is_active(self, bridge) -> bool:
        if isinstance(bridge, LemonSqueezyRevenueBridge):
            return bool(config.LEMONSQUEEZY_ENABLED)
        if isinstance(bridge, GumroadRevenueBridge):
            return bool(config.GUMROAD_ENABLED)
        if isinstance(bridge, BackblazeBridge):
            return bool(config.BACKBLAZE_ENABLED)
        return True

    def publish_product(self, title: str, description: str, price_usd: float) -> dict:
        """Forward to all active bridges; return the first non-simulation result."""
        last: dict = {
            "id": None, "title": title, "price": price_usd, "url": None, "simulation": True,
        }
        for bridge in self._bridges:
            if not self._is_active(bridge):
                continue
            try:
                result = bridge.publish_product(title, description, price_usd)
                if not result.get("simulation"):
                    last = result
            except Exception as exc:
                logger.warning(
                    "[Router] publish_product error (%s): %s", type(bridge).__name__, exc
                )
        return last

    def check_sales(self, product_id: str) -> list[dict]:
        """Aggregate sales from all active bridges."""
        all_sales: list[dict] = []
        for bridge in self._bridges:
            if not self._is_active(bridge):
                continue
            try:
                all_sales.extend(bridge.check_sales(product_id))
            except Exception as exc:
                logger.warning(
                    "[Router] check_sales error (%s): %s", type(bridge).__name__, exc
                )
        return all_sales

    def record_sale_attempt(self, price_usd: float, sold: bool) -> None:
        """Track locally and forward to all active bridges."""
        self._attempts.append({"price_usd": price_usd, "sold": sold})
        for bridge in self._bridges:
            if not self._is_active(bridge):
                continue
            try:
                bridge.record_sale_attempt(price_usd, sold)
            except Exception as exc:
                logger.warning(
                    "[Router] record_sale_attempt error (%s): %s", type(bridge).__name__, exc
                )

    def get_market_feedback(self) -> dict:
        """Return aggregated feedback from the router's own attempt history."""
        total = len(self._attempts)
        if total == 0:
            return {
                "avg_price": 0.0, "conversion_rate": 0.0,
                "total_attempts": 0, "simulation": True,
            }
        sold = [a for a in self._attempts if a["sold"]]
        avg_price = sum(a["price_usd"] for a in sold) / len(sold) if sold else 0.0
        return {
            "avg_price": round(avg_price, 4),
            "conversion_rate": round(len(sold) / total, 4),
            "total_attempts": total,
            "simulation": False,
        }

    # ------------------------------------------------------------------
    # Backblaze B2 integration (storage channel)
    # ------------------------------------------------------------------

    def upload_to_storage(
        self,
        file_path: str | Path,
        file_name: str | None = None,
    ) -> dict:
        """Upload a file to the Backblaze bucket for this router's farm type.

        Args:
            file_path: Local path to the file to upload.
            file_name: Name to use in storage (defaults to original filename).

        Returns:
            dict with: file_id, file_name, bucket, download_url, simulation
            Returns error dict if farm_type not set or storage not enabled.
        """
        if not self._farm_type:
            logger.warning("[Router] upload_to_storage: farm_type not set")
            return {
                "file_id": None,
                "error": "farm_type not configured for this router",
                "simulation": True,
            }

        if not self._storage_bridge:
            # Backblaze not enabled, return simulation result
            logger.info("[Router] upload_to_storage: Backblaze disabled, skipping")
            return {
                "file_id": None,
                "file_name": file_name or Path(file_path).name,
                "bucket": config.BACKBLAZE_BUCKETS.get(self._farm_type),
                "download_url": None,
                "simulation": True,
                "skipped": True,
            }

        try:
            return self._storage_bridge.upload_file(self._farm_type, file_path, file_name)
        except Exception as exc:
            logger.warning("[Router] upload_to_storage error: %s", exc)
            return {
                "file_id": None,
                "error": str(exc),
                "simulation": True,
            }

    def get_download_url(self, file_name: str) -> str | None:
        """Return a signed download URL for a file in this router's farm bucket."""
        if not self._farm_type:
            return None

        if not self._storage_bridge:
            # Return simulated URL if bridge not initialized
            bucket = config.BACKBLAZE_BUCKETS.get(self._farm_type)
            return f"https://f000.backblazeb2.com/file/{bucket}/{file_name}?sim=true" if bucket else None

        return self._storage_bridge.get_download_url(self._farm_type, file_name)

    def delete_from_storage(self, file_name: str) -> bool:
        """Delete a file from Backblaze storage by its file name."""
        if not self._storage_bridge:
            logger.info("[Router] delete_from_storage: Backblaze disabled, skipping")
            return True  # Simulated success

        if not self._farm_type:
            logger.warning("[Router] delete_from_storage: farm_type not set")
            return False

        try:
            return self._storage_bridge.delete_file(self._farm_type, file_name)
        except Exception as exc:
            logger.warning("[Router] delete_from_storage error: %s", exc)
            return False

    def upload_product_to_storage(self, product: dict, file_name: str) -> dict:
        """Upload a product dictionary as a JSON file to Backblaze storage.

        Args:
            product: Product dictionary to upload.
            file_name: Name for the file in storage (e.g. "product_2024-01-15.json").

        Returns:
            dict with upload result (file_id, download_url, etc.)
        """
        import json
        import tempfile
        import os

        if not self._farm_type:
            logger.warning("[Router] upload_product_to_storage: farm_type not set")
            return {"file_id": None, "error": "farm_type not configured", "simulation": True}

        if not self._storage_bridge:
            logger.info("[Router] upload_product_to_storage: Backblaze disabled, skipping")
            return {"file_id": None, "skipped": True, "simulation": True}

        # Write product to temp file
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(product, f, indent=2, ensure_ascii=False)
                temp_path = f.name

            # Upload to storage
            result = self.upload_to_storage(temp_path, file_name)
            logger.info("[Router] upload_product_to_storage: %s -> %s", file_name, result.get("file_id"))
            return result

        except Exception as exc:
            logger.warning("[Router] upload_product_to_storage error: %s", exc)
            return {"file_id": None, "error": str(exc), "simulation": True}

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    # Legacy aliases for backward compatibility
    def upload_to_drive(self, file_path: str | Path, file_name: str | None = None) -> dict:
        """Deprecated: Use upload_to_storage instead."""
        return self.upload_to_storage(file_path, file_name)

    def upload_product_to_drive(self, product: dict, file_name: str) -> dict:
        """Deprecated: Use upload_product_to_storage instead."""
        return self.upload_product_to_storage(product, file_name)
