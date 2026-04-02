"""Shopify revenue bridge.

Shopify Admin REST API capabilities (confirmed 2026-03-30):
  - POST /admin/oauth/access_token              -> OAuth 2.0 Client Credentials token
  - POST /admin/api/{version}/products.json     -> create a product with a default variant
  - GET  /admin/api/{version}/orders.json       -> list orders (all statuses)

Authentication uses the OAuth 2.0 Client Credentials grant.  A token is
requested on the first API call and cached in memory; it is renewed
automatically _EXPIRY_BUFFER seconds before the 86399-second window closes.

Required env vars for live mode:
  SHOPIFY_SHOP          - store prefix only (e.g. "1vm3c9-zm");
                          bridge builds https://{SHOP}.myshopify.com
  SHOPIFY_CLIENT_ID     - OAuth app client ID
  SHOPIFY_CLIENT_SECRET - OAuth app client secret
"""
import logging
import os
import time
import uuid

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)

_API_VERSION = "2024-10"
_EXPIRY_BUFFER = 60  # renew token this many seconds before actual expiry


class ShopifyRevenueBridge:
    """Thin wrapper around the Shopify Admin REST API.

    Runs in **simulation mode** (no network calls) when any of
    *SHOPIFY_SHOP*, *SHOPIFY_CLIENT_ID* or *SHOPIFY_CLIENT_SECRET*
    is absent from the environment.
    """

    def __init__(
        self,
        shop: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.shop: str | None = shop or os.environ.get("SHOPIFY_SHOP")
        self.client_id: str | None = client_id or os.environ.get("SHOPIFY_CLIENT_ID")
        self.client_secret: str | None = client_secret or os.environ.get("SHOPIFY_CLIENT_SECRET")
        self._simulation: bool = not all([self.shop, self.client_id, self.client_secret])
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._attempts: list[dict] = []

        if self._simulation:
            logger.info("[Shopify] Running in simulation mode (credentials absent).")
        else:
            logger.info("[Shopify] Credentials present; live mode active for shop=%s.", self.shop)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _base_url(self) -> str:
        return f"https://{self.shop}.myshopify.com"

    def _headers(self, token: str) -> dict:
        return {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        }

    def _sim_product(self, title: str, price: float) -> dict:
        return {
            "id": f"sim-{uuid.uuid4().hex[:8]}",
            "title": title,
            "price": price,
            "url": None,
            "simulation": True,
        }

    def _refresh_token(self) -> str | None:
        """Request a new access token via the Client Credentials grant."""
        try:
            resp = requests.post(
                f"{self._base_url}/admin/oauth/access_token",
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                    "scope": "write_products,read_products,read_orders",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 86399)
            self._token_expires_at = time.monotonic() + expires_in
            logger.info("[Shopify] Token refreshed; expires in %ds.", expires_in)
            return self._access_token
        except Exception as exc:
            logger.warning("[Shopify] Token refresh failed: %s", exc)
            self._access_token = None
            self._token_expires_at = 0.0
            return None

    def _get_token(self) -> str | None:
        """Return a valid access token, refreshing if necessary."""
        if self._access_token and time.monotonic() < self._token_expires_at - _EXPIRY_BUFFER:
            return self._access_token
        return self._refresh_token()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish_product(
        self,
        title: str,
        description: str,
        price_usd: float,
    ) -> dict:
        """Create a Shopify product and return a product-like dict.

        Uses POST /admin/api/{version}/products.json with a single default
        variant at *price_usd*.  Falls back to simulation on any error or
        missing credentials.
        """
        if self._simulation:
            return self._sim_product(title, price_usd)

        token = self._get_token()
        if not token:
            logger.warning("[Shopify] publish_product: no token available — simulating.")
            return self._sim_product(title, price_usd)

        payload = {
            "product": {
                "title": title,
                "body_html": description,
                "variants": [{"price": f"{price_usd:.2f}"}],
            }
        }

        try:
            resp = requests.post(
                f"{self._base_url}/admin/api/{_API_VERSION}/products.json",
                headers=self._headers(token),
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[Shopify] publish_product HTTP error (%s) — falling back to simulation.", status
            )
            return self._sim_product(title, price_usd)

        product = resp.json().get("product", {})
        product_id = str(product.get("id", ""))
        handle = product.get("handle", "")
        url = f"{self._base_url}/products/{handle}" if handle else None
        logger.info("[Shopify] Product created id=%s handle=%s", product_id, handle)
        return {
            "id": product_id,
            "title": title,
            "price": price_usd,
            "url": url,
            "simulation": False,
        }

    def check_sales(self, product_id: str) -> list[dict]:
        """Return orders that contain *product_id* as a line item.

        Uses GET /admin/api/{version}/orders.json?status=any and filters
        client-side by matching line_items[].product_id.
        """
        if self._simulation:
            return []

        token = self._get_token()
        if not token:
            return []

        try:
            resp = requests.get(
                f"{self._base_url}/admin/api/{_API_VERSION}/orders.json",
                headers=self._headers(token),
                params={"status": "any"},
                timeout=10,
            )
            resp.raise_for_status()
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.warning(
                "[Shopify] check_sales HTTP error (%s) — returning empty list.", status
            )
            return []

        result = []
        for order in resp.json().get("orders", []):
            for item in order.get("line_items", []):
                if str(item.get("product_id", "")) == str(product_id):
                    result.append({
                        "id": str(order["id"]),
                        "total_usd": float(order.get("total_price", 0)),
                        "status": order.get("financial_status"),
                        "created_at": order.get("created_at"),
                    })
                    break
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
