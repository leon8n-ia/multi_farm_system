"""Revenue bridge router — fan-out to multiple bridges.

Routes publish_product, check_sales, record_sale_attempt and
get_market_feedback to all registered bridges.

Additionally supports GoogleDriveBridge for file uploads as a
secondary distribution channel.

Bridge activation is controlled by config flags:
  - LemonSqueezyRevenueBridge: config.LEMONSQUEEZY_ENABLED (PERMANENTLY DISABLED)
  - GumroadRevenueBridge: config.GUMROAD_ENABLED
  - GoogleDriveBridge: config.GOOGLE_DRIVE_ENABLED

All exceptions from individual bridge calls are caught and logged so
a broken bridge never interrupts the simulation cycle.
"""
import logging
from pathlib import Path

import config
from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge
from farms.gumroad_bridge import GumroadRevenueBridge
from farms.shared.google_drive_bridge import GoogleDriveBridge

logger = logging.getLogger(__name__)


class RevenueBridgeRouter:
    """Fan-out router for multiple revenue bridges.

    Args:
        bridges: Ordered list of bridge instances.  Activation is controlled
                 by config flags (LEMONSQUEEZY_ENABLED, GUMROAD_ENABLED).
                 LemonSqueezy is permanently disabled.
        farm_type: Farm type for Google Drive folder routing (optional).
    """

    def __init__(self, bridges: list, farm_type: str | None = None) -> None:
        self._bridges = bridges
        self._attempts: list[dict] = []
        self._farm_type = farm_type
        self._drive_bridge: GoogleDriveBridge | None = None

        # Initialize Google Drive bridge if enabled and farm_type provided
        if farm_type and config.GOOGLE_DRIVE_ENABLED:
            self._drive_bridge = GoogleDriveBridge()
            logger.info("[Router] GoogleDriveBridge enabled for farm_type=%s", farm_type)

    def _is_active(self, bridge) -> bool:
        if isinstance(bridge, LemonSqueezyRevenueBridge):
            return bool(config.LEMONSQUEEZY_ENABLED)
        if isinstance(bridge, GumroadRevenueBridge):
            return bool(config.GUMROAD_ENABLED)
        if isinstance(bridge, GoogleDriveBridge):
            return bool(config.GOOGLE_DRIVE_ENABLED)
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
    # Google Drive integration (additional channel)
    # ------------------------------------------------------------------

    def upload_to_drive(
        self,
        file_path: str | Path,
        file_name: str | None = None,
    ) -> dict:
        """Upload a file to the Google Drive folder for this router's farm type.

        Args:
            file_path: Local path to the file to upload.
            file_name: Name to use in Drive (defaults to original filename).

        Returns:
            dict with: file_id, file_name, folder_id, web_view_link, simulation
            Returns error dict if farm_type not set or drive not enabled.
        """
        if not self._farm_type:
            logger.warning("[Router] upload_to_drive: farm_type not set")
            return {
                "file_id": None,
                "error": "farm_type not configured for this router",
                "simulation": True,
            }

        if not self._drive_bridge:
            # Google Drive not enabled, return simulation result
            logger.info("[Router] upload_to_drive: Google Drive disabled, skipping")
            return {
                "file_id": None,
                "file_name": file_name or Path(file_path).name,
                "folder_id": config.GOOGLE_DRIVE_FOLDER_IDS.get(self._farm_type),
                "web_view_link": None,
                "simulation": True,
                "skipped": True,
            }

        try:
            return self._drive_bridge.upload_file(self._farm_type, file_path, file_name)
        except Exception as exc:
            logger.warning("[Router] upload_to_drive error: %s", exc)
            return {
                "file_id": None,
                "error": str(exc),
                "simulation": True,
            }

    def get_drive_folder_link(self) -> str | None:
        """Return the public Google Drive folder link for this router's farm type."""
        if not self._farm_type:
            return None

        if self._drive_bridge:
            return self._drive_bridge.get_folder_link(self._farm_type)

        # Return static link even if bridge not initialized
        from farms.shared.google_drive_bridge import DRIVE_FOLDER_LINKS
        return DRIVE_FOLDER_LINKS.get(self._farm_type)

    def delete_from_drive(self, file_id: str) -> bool:
        """Delete a file from Google Drive by its file ID."""
        if not self._drive_bridge:
            logger.info("[Router] delete_from_drive: Google Drive disabled, skipping")
            return True  # Simulated success

        try:
            return self._drive_bridge.delete_file(file_id)
        except Exception as exc:
            logger.warning("[Router] delete_from_drive error: %s", exc)
            return False
