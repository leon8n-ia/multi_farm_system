"""
Tests for PayPalBridge.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from access_server.paypal_bridge import PayPalBridge, PayPalResponse


class TestPayPalBridgeSimulation(unittest.TestCase):
    """Test PayPalBridge in simulation mode (PAYPAL_ENABLED=False)."""

    def setUp(self):
        """Set up test fixtures."""
        # Force simulation mode
        with patch.dict(os.environ, {"PAYPAL_ENABLED": "false"}):
            self.bridge = PayPalBridge(sandbox=True)
            self.bridge.enabled = False

    def test_create_product_simulation(self):
        """Test product creation in simulation mode."""
        response = self.bridge.create_product(
            name="Test Product",
            description="A test product"
        )

        self.assertTrue(response.success)
        self.assertIsNotNone(response.data)
        self.assertIn("id", response.data)
        self.assertTrue(response.data["id"].startswith("PROD-SIMULATED-"))
        self.assertEqual(response.data["name"], "Test Product")

    def test_create_plan_simulation(self):
        """Test plan creation in simulation mode."""
        response = self.bridge.create_plan(
            product_id="PROD-TEST-123",
            name="Monthly Plan",
            price_usd=9.99,
            interval="MONTH"
        )

        self.assertTrue(response.success)
        self.assertIsNotNone(response.data)
        self.assertIn("id", response.data)
        self.assertTrue(response.data["id"].startswith("P-SIMULATED-"))
        self.assertEqual(response.data["status"], "ACTIVE")

    def test_get_subscription_status_simulation(self):
        """Test subscription status check in simulation mode."""
        response = self.bridge.get_subscription_status("I-TEST-SUB-123")

        self.assertTrue(response.success)
        self.assertIsNotNone(response.data)
        self.assertEqual(response.data["status"], "ACTIVE")

    def test_cancel_subscription_simulation(self):
        """Test subscription cancellation in simulation mode."""
        response = self.bridge.cancel_subscription("I-TEST-SUB-123")

        self.assertTrue(response.success)
        self.assertEqual(response.data["status"], "CANCELLED")

    def test_is_subscription_active_simulation(self):
        """Test convenience method for active check."""
        result = self.bridge.is_subscription_active("I-TEST-SUB-123")
        self.assertTrue(result)


class TestPayPalBridgeWithMocks(unittest.TestCase):
    """Test PayPalBridge with mocked HTTP requests."""

    def setUp(self):
        """Set up test fixtures with enabled bridge."""
        self.bridge = PayPalBridge(sandbox=True)
        self.bridge.enabled = True

    @patch("access_server.paypal_bridge.requests.request")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_ID", "test_client_id")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_SECRET", "test_secret")
    def test_authentication_success(self, mock_request):
        """Test successful OAuth2 authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"access_token": "test_token", "expires_in": 3600}'
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600
        }
        mock_request.return_value = mock_response

        token = self.bridge._get_access_token()

        self.assertEqual(token, "test_token")
        self.assertIsNotNone(self.bridge._access_token)

    @patch("access_server.paypal_bridge.requests.request")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_ID", "test_client_id")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_SECRET", "test_secret")
    def test_create_product_api_call(self, mock_request):
        """Test product creation API call."""
        # First call for auth, second for product creation
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.content = b'{"access_token": "test_token", "expires_in": 3600}'
        auth_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600
        }

        product_response = MagicMock()
        product_response.status_code = 201
        product_response.content = b'{"id": "PROD-123", "name": "Test"}'
        product_response.json.return_value = {
            "id": "PROD-123",
            "name": "Test"
        }

        mock_request.side_effect = [auth_response, product_response]

        response = self.bridge.create_product(
            name="Test Product",
            description="Description"
        )

        self.assertTrue(response.success)
        self.assertEqual(response.data["id"], "PROD-123")

    @patch("access_server.paypal_bridge.requests.request")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_ID", "test_client_id")
    @patch("access_server.paypal_bridge.PAYPAL_CLIENT_SECRET", "test_secret")
    def test_retry_on_server_error(self, mock_request):
        """Test retry logic on server errors."""
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.content = b'{"access_token": "test_token", "expires_in": 3600}'
        auth_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600
        }

        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"
        error_response.content = b''

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.content = b'{"id": "I-123", "status": "ACTIVE"}'
        success_response.json.return_value = {
            "id": "I-123",
            "status": "ACTIVE"
        }

        # Auth, fail, fail, success
        mock_request.side_effect = [
            auth_response,
            error_response,
            error_response,
            success_response
        ]

        with patch("access_server.paypal_bridge.time.sleep"):
            response = self.bridge.get_subscription_status("I-123")

        self.assertTrue(response.success)
        self.assertEqual(response.data["status"], "ACTIVE")


class TestPayPalResponse(unittest.TestCase):
    """Test PayPalResponse dataclass."""

    def test_success_response(self):
        """Test successful response creation."""
        response = PayPalResponse(success=True, data={"id": "123"})
        self.assertTrue(response.success)
        self.assertEqual(response.data["id"], "123")
        self.assertIsNone(response.error)

    def test_error_response(self):
        """Test error response creation."""
        response = PayPalResponse(success=False, error="Something went wrong")
        self.assertFalse(response.success)
        self.assertIsNone(response.data)
        self.assertEqual(response.error, "Something went wrong")


if __name__ == "__main__":
    unittest.main()
