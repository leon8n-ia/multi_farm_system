"""Payhip revenue bridge.

Payhip API v2 capabilities (confirmed 2026-03-29):
  - POST /api/v2/coupons     → create a discount coupon
  - GET  /api/v2/coupons     → list coupons
  - GET  /api/v2/coupons/:id → get a coupon
  - GET  /api/v2/license/verify / PUT .../disable|enable|usage|decrease

IMPORTANT — No product or order endpoints:
  Payhip's public API does NOT support creating products or listing
  sales/orders programmatically.  publish_product() and check_sales()
  therefore always run in simulation mode regardless of whether an API
  key is present.  record_sale_attempt() / get_market_feedback() still
  work as in-process feedback accumulators (same pattern as the
  LemonSqueezy bridge).

Authentication (live coupon/license calls):
  Header:  payhip-api-key: <key>

Required env vars for live coupon/license operations:
  PAYHIP_API_KEY  – API key from Account → Developer Settings
"""
import logging
import os
import uuid

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)

_BASE_URL = "https://payhip.com/api/v2"


class PayhipRevenueBridge:
    """Thin wrapper around the Payhip API v2.

    Runs in **simulation mode** (no network calls) when *PAYHIP_API_KEY*
    is absent from the environment.

    publish_product() and check_sales() are always simulated because
    Payhip's public API does not expose product-creation or order-listing
    endpoints.  The bridge still tracks sale attempts internally so that
    get_market_feedback() produces useful signals for the mutation engine.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key: str | None = api_key or os.environ.get("PAYHIP_API_KEY")
        self._simulation: bool = not bool(self.api_key)
        self._attempts: list[dict] = []

        if self._simulation:
            logger.info("[Payhip] Running in simulation mode (no API key).")
        else:
            logger.info("[Payhip] API key present; coupon/license operations are live.")
            logger.info(
                "[Payhip] publish_product and check_sales always simulated "
                "(Payhip API has no product/order endpoints)."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {"payhip-api-key": self.api_key or ""}

    def _sim_product(self, title: str, price: float) -> dict:
        return {
            "id": f"sim-{uuid.uuid4().hex[:8]}",
            "title": title,
            "price": price,
            "url": None,
            "simulation": True,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_product(
        self,
        title: str,
        description: str,
        price_usd: float,
    ) -> dict:
        """Return a simulated product listing dict.

        Payhip's public API has no endpoint for creating products, so
        this method always returns a simulation dict.  The return shape
        is identical to LemonSqueezyRevenueBridge.publish_product so that
        callers can treat both bridges interchangeably.
        """
        logger.debug(
            "[Payhip] publish_product called (always simulated): title=%r price=%.2f",
            title,
            price_usd,
        )
        return self._sim_product(title, price_usd)

    def check_sales(self, product_id: str) -> list[dict]:
        """Return an empty list.

        Payhip's public API has no endpoint for listing orders or sales.
        Callers should rely on record_sale_attempt() + get_market_feedback()
        for in-process feedback instead.
        """
        logger.debug(
            "[Payhip] check_sales called (always simulated): product_id=%r", product_id
        )
        return []

    def get_market_feedback(self) -> dict:
        """Summarise accumulated sale attempts as market feedback."""
        total = len(self._attempts)
        if total == 0:
            return {
                "avg_price": 0.0,
                "conversion_rate": 0.0,
                "total_attempts": 0,
                "simulation": self._simulation,
            }

        sold = [a for a in self._attempts if a["sold"]]
        avg_price = sum(a["price_usd"] for a in sold) / len(sold) if sold else 0.0
        conversion_rate = len(sold) / total

        return {
            "avg_price": round(avg_price, 4),
            "conversion_rate": round(conversion_rate, 4),
            "total_attempts": total,
            "simulation": self._simulation,
        }

    def record_sale_attempt(self, price_usd: float, sold: bool) -> None:
        """Record the outcome of a single sale attempt for feedback tracking."""
        self._attempts.append({"price_usd": price_usd, "sold": sold})
