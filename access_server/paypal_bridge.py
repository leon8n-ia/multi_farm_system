"""
PayPal Subscriptions API bridge for Multi Farm System.

Replaces Dodo Payments as the payment processor.
Uses PayPal REST API directly with requests (no external SDK).
"""
import os
import time
import logging
from typing import Optional
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Environment configuration
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_ENABLED = os.getenv("PAYPAL_ENABLED", "true").lower() == "true"

# API endpoints
SANDBOX_URL = "https://api-m.sandbox.paypal.com"
PRODUCTION_URL = "https://api-m.paypal.com"


@dataclass
class PayPalResponse:
    """Standardized response from PayPal operations."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class PayPalBridge:
    """
    Bridge to PayPal Subscriptions API.

    Handles authentication, product/plan creation, and subscription management.
    Supports simulation mode when PAYPAL_ENABLED=False.
    """

    def __init__(self, sandbox: bool = True):
        """
        Initialize PayPal bridge.

        Args:
            sandbox: If True, use sandbox environment. Default True.
        """
        self.sandbox = sandbox
        self.base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self.enabled = PAYPAL_ENABLED
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        if self.enabled and (not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET):
            logger.warning(
                "PayPal credentials not configured. "
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET."
            )

    def _get_access_token(self) -> Optional[str]:
        """
        Get OAuth2 access token from PayPal.

        Caches token until expiration.

        Returns:
            Access token string or None if authentication fails.
        """
        # Return cached token if still valid
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.base_url}/v1/oauth2/token"

        response = self._request_with_retry(
            method="POST",
            url=url,
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            skip_auth=True
        )

        if response.success and response.data:
            self._access_token = response.data.get("access_token")
            expires_in = response.data.get("expires_in", 3600)
            # Expire 60 seconds early to avoid edge cases
            self._token_expires_at = time.time() + expires_in - 60
            logger.info("PayPal access token acquired successfully")
            return self._access_token

        logger.error(f"Failed to get PayPal access token: {response.error}")
        return None

    def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        skip_auth: bool = False,
        **kwargs
    ) -> PayPalResponse:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            url: Full URL to request
            max_retries: Number of retry attempts (default 3)
            skip_auth: If True, skip adding Bearer token
            **kwargs: Additional arguments passed to requests

        Returns:
            PayPalResponse with success status and data or error.
        """
        if not skip_auth:
            token = self._get_access_token()
            if not token:
                return PayPalResponse(
                    success=False,
                    error="Failed to authenticate with PayPal"
                )
            kwargs.setdefault("headers", {})
            kwargs["headers"]["Authorization"] = f"Bearer {token}"
            kwargs["headers"].setdefault("Content-Type", "application/json")

        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(
                    f"PayPal API request attempt {attempt}/{max_retries}: "
                    f"{method} {url}"
                )

                response = requests.request(method, url, timeout=30, **kwargs)

                # Success responses
                if response.status_code in (200, 201, 204):
                    data = response.json() if response.content else {}
                    logger.info(
                        f"PayPal API success: {method} {url} -> {response.status_code}"
                    )
                    return PayPalResponse(success=True, data=data)

                # Client errors (don't retry)
                if 400 <= response.status_code < 500:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("message", response.text)
                    logger.error(
                        f"PayPal API client error: {method} {url} -> "
                        f"{response.status_code}: {error_msg}"
                    )
                    return PayPalResponse(success=False, error=error_msg)

                # Server errors (retry)
                last_error = f"HTTP {response.status_code}: {response.text}"
                logger.warning(
                    f"PayPal API server error (attempt {attempt}): {last_error}"
                )

            except requests.exceptions.Timeout:
                last_error = "Request timeout"
                logger.warning(f"PayPal API timeout (attempt {attempt})")

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.warning(
                    f"PayPal API request error (attempt {attempt}): {last_error}"
                )

            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.debug(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)

        logger.error(f"PayPal API failed after {max_retries} attempts: {last_error}")
        return PayPalResponse(success=False, error=last_error)

    def create_product(self, name: str, description: str) -> PayPalResponse:
        """
        Create a product in PayPal catalog.

        Products are the foundation for subscription plans.

        Args:
            name: Product name (e.g., "Data Cleaning Farm Access")
            description: Product description

        Returns:
            PayPalResponse with product data including 'id' on success.
        """
        if not self.enabled:
            logger.info(f"[SIMULATION] create_product: {name}")
            return PayPalResponse(
                success=True,
                data={
                    "id": f"PROD-SIMULATED-{name[:8].upper()}",
                    "name": name,
                    "description": description,
                    "type": "SERVICE",
                    "category": "SOFTWARE"
                }
            )

        url = f"{self.base_url}/v1/catalogs/products"
        payload = {
            "name": name,
            "description": description,
            "type": "SERVICE",
            "category": "SOFTWARE"
        }

        return self._request_with_retry("POST", url, json=payload)

    def create_plan(
        self,
        product_id: str,
        name: str,
        price_usd: float,
        interval: str = "MONTH"
    ) -> PayPalResponse:
        """
        Create a subscription plan for a product.

        Args:
            product_id: PayPal product ID from create_product()
            name: Plan name (e.g., "Monthly Access")
            price_usd: Price in USD (e.g., 9.99)
            interval: Billing interval - "DAY", "WEEK", "MONTH", "YEAR"

        Returns:
            PayPalResponse with plan data including 'id' on success.
        """
        if not self.enabled:
            logger.info(
                f"[SIMULATION] create_plan: {name} @ ${price_usd}/{interval}"
            )
            return PayPalResponse(
                success=True,
                data={
                    "id": f"P-SIMULATED-{name[:8].upper()}",
                    "product_id": product_id,
                    "name": name,
                    "status": "ACTIVE",
                    "billing_cycles": [{
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": str(price_usd),
                                "currency_code": "USD"
                            }
                        }
                    }]
                }
            )

        url = f"{self.base_url}/v1/billing/plans"
        payload = {
            "product_id": product_id,
            "name": name,
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {
                        "interval_unit": interval.upper(),
                        "interval_count": 1
                    },
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,  # Infinite
                    "pricing_scheme": {
                        "fixed_price": {
                            "value": str(price_usd),
                            "currency_code": "USD"
                        }
                    }
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "payment_failure_threshold": 3
            }
        }

        return self._request_with_retry("POST", url, json=payload)

    def get_subscription_status(self, subscription_id: str) -> PayPalResponse:
        """
        Get the current status of a subscription.

        Args:
            subscription_id: PayPal subscription ID (starts with I-)

        Returns:
            PayPalResponse with subscription data including 'status'.
            Status values: APPROVAL_PENDING, APPROVED, ACTIVE,
            SUSPENDED, CANCELLED, EXPIRED
        """
        if not self.enabled:
            logger.info(
                f"[SIMULATION] get_subscription_status: {subscription_id}"
            )
            return PayPalResponse(
                success=True,
                data={
                    "id": subscription_id,
                    "status": "ACTIVE",
                    "status_update_time": "2024-01-01T00:00:00Z"
                }
            )

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}"
        return self._request_with_retry("GET", url)

    def cancel_subscription(
        self,
        subscription_id: str,
        reason: str = "Cancelled by user"
    ) -> PayPalResponse:
        """
        Cancel an active subscription.

        Args:
            subscription_id: PayPal subscription ID (starts with I-)
            reason: Cancellation reason for records

        Returns:
            PayPalResponse with success=True if cancelled.
        """
        if not self.enabled:
            logger.info(
                f"[SIMULATION] cancel_subscription: {subscription_id}"
            )
            return PayPalResponse(success=True, data={"status": "CANCELLED"})

        url = f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
        payload = {"reason": reason}

        response = self._request_with_retry("POST", url, json=payload)

        # PayPal returns 204 No Content on success
        if response.success:
            return PayPalResponse(success=True, data={"status": "CANCELLED"})

        return response

    def is_subscription_active(self, subscription_id: str) -> bool:
        """
        Check if a subscription is currently active.

        Convenience method that wraps get_subscription_status.

        Args:
            subscription_id: PayPal subscription ID

        Returns:
            True if subscription status is ACTIVE, False otherwise.
        """
        response = self.get_subscription_status(subscription_id)
        if response.success and response.data:
            return response.data.get("status") == "ACTIVE"
        return False


# Singleton instance for convenience
_bridge_instance: Optional[PayPalBridge] = None


def get_paypal_bridge(sandbox: bool = None) -> PayPalBridge:
    """
    Get or create singleton PayPal bridge instance.

    Args:
        sandbox: Use sandbox environment. If None, reads from PAYPAL_SANDBOX env var.
                 Defaults to False (production) if env var is not set.

    Returns:
        PayPalBridge instance
    """
    global _bridge_instance
    if _bridge_instance is None:
        if sandbox is None:
            sandbox = os.getenv("PAYPAL_SANDBOX", "false").lower() == "true"
        _bridge_instance = PayPalBridge(sandbox=sandbox)
    return _bridge_instance
