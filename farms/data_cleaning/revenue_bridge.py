"""Lemon Squeezy revenue bridge.

Lemon Squeezy API v1 capabilities (confirmed 2026-03-27):
  - POST /v1/checkouts    → creates a shareable checkout URL for an existing variant
  - GET  /v1/orders       → list orders / sales for a store
  - GET  /v1/products     → list products (read-only; no POST equivalent)
  - GET  /v1/variants     → list variants (read-only; no POST equivalent)

Creating products programmatically is NOT supported.  publish_product()
therefore creates a checkout link (POST /checkouts) for a pre-existing
variant, which serves as the "live listing URL" returned to the caller.

IMPORTANT — custom_price units:
  Lemon Squeezy expects custom_price in the STORE's currency (not USD),
  expressed in the smallest unit (centavos for ARS, cents for USD, etc.).
  The caller passes price_in_store_currency (a float in the store's major
  unit, e.g. 1000.0 for ARS 1000).  The bridge converts to minor units
  by multiplying by 100.

Required env vars for live mode:
  LEMONSQUEEZY_API_TOKEN  – API key from Settings → API
  LEMONSQUEEZY_STORE_ID   – numeric store ID
  LEMONSQUEEZY_VARIANT_ID – (optional) variant to attach checkouts to;
                            if absent, auto-discovered from the first
                            product in the store.
"""
import logging
import os
import uuid

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.lemonsqueezy.com/v1"
_JSON_API_HEADERS = {
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json",
}


class LemonSqueezyRevenueBridge:
    """Thin wrapper around the Lemon Squeezy API v1.

    Runs in **simulation mode** (no network calls) when
    *LEMONSQUEEZY_API_TOKEN* is absent from the environment.
    """

    def __init__(
        self,
        api_token: str | None = None,
        store_id: str | None = None,
        variant_id: str | None = None,
    ) -> None:
        self.api_token: str | None = api_token or os.environ.get("LEMONSQUEEZY_API_TOKEN")
        self.store_id: str | None = store_id or os.environ.get("LEMONSQUEEZY_STORE_ID")
        self.variant_id: str | None = variant_id or os.environ.get("LEMONSQUEEZY_VARIANT_ID")
        self._simulation: bool = not bool(self.api_token)
        self._attempts: list[dict] = []

        if self._simulation:
            logger.info("[LemonSqueezy] Running in simulation mode (no API token).")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {**_JSON_API_HEADERS, "Authorization": f"Bearer {self.api_token}"}

    def _discover_variant_id(self) -> str | None:
        """Return the first available variant id for *store_id*, or None."""
        if not self.store_id:
            return None
        try:
            r = requests.get(
                f"{_BASE_URL}/products",
                headers=self._headers,
                params={"filter[store_id]": self.store_id, "page[size]": 1},
                timeout=10,
            )
            r.raise_for_status()
            products = r.json().get("data", [])
            if not products:
                logger.warning("[LemonSqueezy] No products found in store %s.", self.store_id)
                return None
            product_id = products[0]["id"]

            r2 = requests.get(
                f"{_BASE_URL}/variants",
                headers=self._headers,
                params={"filter[product_id]": product_id, "page[size]": 1},
                timeout=10,
            )
            r2.raise_for_status()
            variants = r2.json().get("data", [])
            if not variants:
                logger.warning("[LemonSqueezy] No variants for product %s.", product_id)
                return None
            return variants[0]["id"]
        except Exception as exc:
            logger.warning("[LemonSqueezy] variant discovery failed: %s", exc)
            return None

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
        price_in_store_currency: float,
    ) -> dict:
        """Create a Lemon Squeezy checkout and return a product-like dict.

        *price_in_store_currency* is the price in the store's major currency
        unit (e.g. 1000.0 for ARS 1000 or 9.99 for USD 9.99).  The bridge
        converts to minor units (× 100) before sending to the API.

        Uses POST /v1/checkouts with a custom_price so each sale cycle
        gets a fresh checkout URL at the correct price.  Falls back to
        simulation on any error or missing credentials.
        """
        if self._simulation or not self.store_id:
            return self._sim_product(title, price_in_store_currency)

        variant_id = self.variant_id or self._discover_variant_id()
        if not variant_id:
            logger.warning(
                "[LemonSqueezy] No variant_id available for store %s — simulating.", self.store_id
            )
            return self._sim_product(title, price_in_store_currency)

        payload = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "custom_price": int(price_in_store_currency * 100),  # minor currency unit
                    "product_options": {
                        "name": title,
                        "description": description,
                    },
                },
                "relationships": {
                    "store": {
                        "data": {"type": "stores", "id": str(self.store_id)}
                    },
                    "variant": {
                        "data": {"type": "variants", "id": str(variant_id)}
                    },
                },
            }
        }

        try:
            resp = requests.post(
                f"{_BASE_URL}/checkouts",
                headers=self._headers,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[LemonSqueezy] publish_product HTTP error (%s) — falling back to simulation.", status
            )
            return self._sim_product(title, price_in_store_currency)

        data = resp.json().get("data", {})
        attrs = data.get("attributes", {})
        logger.info("[LemonSqueezy] Checkout created id=%s url=%s", data.get("id"), attrs.get("url"))
        return {
            "id": data.get("id"),
            "title": title,
            "price": price_in_store_currency,
            "url": attrs.get("url"),
            "simulation": False,
        }

    def check_sales(self, product_id: str) -> list[dict]:
        """Return orders from the store that match *product_id*.

        Uses GET /v1/orders filtered by store_id, then filters client-side
        by product_id via the first_order_item field.
        """
        if self._simulation:
            return []

        try:
            resp = requests.get(
                f"{_BASE_URL}/orders",
                headers=self._headers,
                params={
                    "filter[store_id]": self.store_id,
                    "page[size]": 50,
                },
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[LemonSqueezy] check_sales HTTP error (%s) — returning empty list.", status
            )
            return []

        result = []
        for order in resp.json().get("data", []):
            attrs = order.get("attributes", {})
            first_item = attrs.get("first_order_item") or {}
            if str(first_item.get("product_id", "")) == str(product_id):
                result.append({
                    "id": order["id"],
                    "total_usd": (attrs.get("total_usd") or 0) / 100,
                    "status": attrs.get("status"),
                    "created_at": attrs.get("created_at"),
                })
        return result

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
