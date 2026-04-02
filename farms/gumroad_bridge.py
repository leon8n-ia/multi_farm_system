"""Gumroad revenue bridge.

Gumroad API v2 capabilities (confirmed 2026-03-31):
  - PUT  /v2/products/:id        → update product name / price / description
  - GET  /v2/products/:id/sales  → list sales for a product

Creating products via POST /v2/products is NOT supported by Gumroad's API.
publish_product() therefore always simulates when no product_id is given.
When a *product_id* is provided at construction, publish_product() sends a
PUT to update the existing product's price and description.

Pre-existing product IDs (as of 2026-03-31):
  data_cleaning:     fpwkdg
  auto_reports:      frhqhf
  product_listing:   jzzsv
  monetized_content: wnuah

IMPORTANT — price units:
  Gumroad expects price in USD cents (integer, e.g. 999 for $9.99).
  The caller passes price_usd as a float in major units.  The bridge
  converts with round(price_usd * 100).

Required env var for live mode:
  GUMROAD_ACCESS_TOKEN  – personal access token (Gumroad Settings → Advanced)
"""
import logging
import os
import uuid

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.gumroad.com/v2"


class GumroadRevenueBridge:
    """Thin wrapper around the Gumroad API v2.

    Runs in **simulation mode** (no network calls) when
    *GUMROAD_ACCESS_TOKEN* is absent from the environment.

    Args:
        access_token: Personal access token; falls back to
                      GUMROAD_ACCESS_TOKEN env var.
        product_id:   Pre-existing Gumroad product ID (permalink, e.g. "fpwkdg").
                      When supplied, publish_product() updates the product via
                      PUT instead of creating a new one via POST.
    """

    def __init__(
        self,
        access_token: str | None = None,
        product_id: str | None = None,
    ) -> None:
        self.access_token: str | None = access_token or os.environ.get("GUMROAD_ACCESS_TOKEN")
        self.product_id: str | None = product_id
        self._simulation: bool = not bool(self.access_token)
        self._attempts: list[dict] = []

        if self._simulation:
            logger.info("[Gumroad] Running in simulation mode (no access token).")
        else:
            logger.info(
                "[Gumroad] Live mode active. product_id=%s",
                self.product_id or "not set (will create on publish)",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

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
        """Update a Gumroad product and return a product-like dict.

        Gumroad's API does not support creating products programmatically
        (POST /v2/products is not available).  When no *product_id* was
        supplied at construction, this method always returns a simulation
        dict — it logs the attempt but makes no network call.

        When *product_id* is set, sends PUT /v2/products/{id} to update
        the existing product's name, description, and price.

        *price_usd* is converted to USD cents before sending.
        Falls back to simulation on any error or missing credentials.
        """
        if self._simulation or not self.product_id:
            if not self._simulation:
                logger.info(
                    "[Gumroad] publish_product: no product_id set — "
                    "Gumroad API does not support product creation; simulating."
                )
            return self._sim_product(title, price_usd)

        price_cents = round(price_usd * 100)
        payload = {
            "name": title,
            "description": description,
            "price": price_cents,
        }

        try:
            resp = requests.put(
                f"{_BASE_URL}/products/{self.product_id}",
                headers=self._headers,
                data=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[Gumroad] publish_product HTTP error (%s) — falling back to simulation.", status
            )
            return self._sim_product(title, price_usd)

        body = resp.json()
        if not body.get("success"):
            logger.warning("[Gumroad] publish_product: API returned success=false — simulating.")
            return self._sim_product(title, price_usd)

        product = body.get("product", {})
        product_id = product.get("id", "")
        url = product.get("short_url")
        logger.info("[Gumroad] Product updated id=%s url=%s", product_id, url)
        return {
            "id": str(product_id),
            "title": title,
            "price": price_usd,
            "url": url,
            "simulation": False,
        }

    def check_sales(self, product_id: str) -> list[dict]:
        """Return sales for *product_id*.

        Uses GET /v2/products/{product_id}/sales.
        Returns a list of dicts with id, total_usd, status, created_at.
        """
        if self._simulation:
            return []

        try:
            resp = requests.get(
                f"{_BASE_URL}/products/{product_id}/sales",
                headers=self._headers,
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[Gumroad] check_sales HTTP error (%s) — returning empty list.", status
            )
            return []

        body = resp.json()
        if not body.get("success"):
            logger.warning("[Gumroad] check_sales: API returned success=false.")
            return []

        result = []
        for sale in body.get("sales", []):
            if sale.get("refunded"):
                sale_status = "refunded"
            elif sale.get("chargebacked"):
                sale_status = "chargebacked"
            else:
                sale_status = "paid"
            result.append({
                "id": sale.get("id"),
                "total_usd": (sale.get("price") or 0) / 100,
                "status": sale_status,
                "created_at": sale.get("created_at"),
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
