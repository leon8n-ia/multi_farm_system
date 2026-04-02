"""Tests for ShopifyRevenueBridge — no real network calls."""
import time
import pytest
from unittest.mock import MagicMock, patch

from requests import HTTPError

from farms.shopify_bridge import ShopifyRevenueBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_error(status_code: int) -> HTTPError:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return HTTPError(response=mock_resp)


def _token_response(token: str = "test-token", expires_in: int = 86399) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"access_token": token, "expires_in": expires_in}
    return mock


def _product_response(product_id: int = 123, handle: str = "test-product") -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {
        "product": {
            "id": product_id,
            "handle": handle,
            "title": "Test",
            "variants": [{"id": 456, "price": "9.99"}],
        }
    }
    return mock


def _orders_response(orders: list[dict] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"orders": orders or []}
    return mock


def _order(order_id: str, product_id: str, total_price: str = "25.00") -> dict:
    return {
        "id": order_id,
        "financial_status": "paid",
        "total_price": total_price,
        "created_at": "2026-01-01T00:00:00Z",
        "line_items": [{"product_id": product_id, "title": "Test Product"}],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge():
    """No credentials -> simulation mode."""
    return ShopifyRevenueBridge()


@pytest.fixture
def live_bridge():
    """Full credentials supplied directly — no env required."""
    return ShopifyRevenueBridge(
        shop="test-shop",
        client_id="client-id-123",
        client_secret="client-secret-xyz",
    )


# ---------------------------------------------------------------------------
# Simulation mode detection
# ---------------------------------------------------------------------------

class TestSimulationMode:
    def test_no_credentials_is_simulation(self, bridge):
        assert bridge._simulation is True

    def test_explicit_credentials_not_simulation(self, live_bridge):
        assert live_bridge._simulation is False

    def test_missing_shop_is_simulation(self):
        b = ShopifyRevenueBridge(shop=None, client_id="cid", client_secret="csec")
        assert b._simulation is True

    def test_missing_client_id_is_simulation(self):
        b = ShopifyRevenueBridge(shop="myshop", client_id=None, client_secret="csec")
        assert b._simulation is True

    def test_missing_client_secret_is_simulation(self):
        b = ShopifyRevenueBridge(shop="myshop", client_id="cid", client_secret=None)
        assert b._simulation is True

    def test_env_vars_activate_live_mode(self, monkeypatch):
        monkeypatch.setenv("SHOPIFY_SHOP", "env-shop")
        monkeypatch.setenv("SHOPIFY_CLIENT_ID", "env-cid")
        monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "env-csec")
        b = ShopifyRevenueBridge()
        assert b._simulation is False

    def test_partial_env_vars_stays_simulation(self, monkeypatch):
        monkeypatch.setenv("SHOPIFY_SHOP", "env-shop")
        monkeypatch.delenv("SHOPIFY_CLIENT_ID", raising=False)
        monkeypatch.delenv("SHOPIFY_CLIENT_SECRET", raising=False)
        b = ShopifyRevenueBridge()
        assert b._simulation is True

    def test_shop_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("SHOPIFY_SHOP", "my-shop")
        monkeypatch.setenv("SHOPIFY_CLIENT_ID", "cid")
        monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "csec")
        b = ShopifyRevenueBridge()
        assert b.shop == "my-shop"


# ---------------------------------------------------------------------------
# Token refresh / caching
# ---------------------------------------------------------------------------

class TestTokenRefresh:
    def test_token_fetched_on_first_call(self, live_bridge):
        with patch("requests.post", return_value=_token_response("tok-1")) as mock_post:
            token = live_bridge._get_token()
        assert token == "tok-1"
        mock_post.assert_called_once()

    def test_token_cached_avoids_second_request(self, live_bridge):
        with patch("requests.post", return_value=_token_response("tok-1")) as mock_post:
            live_bridge._get_token()
            live_bridge._get_token()
        mock_post.assert_called_once()

    def test_expired_token_triggers_refresh(self, live_bridge):
        live_bridge._access_token = "old-token"
        live_bridge._token_expires_at = time.monotonic() - 1  # already expired
        with patch("requests.post", return_value=_token_response("new-token")) as mock_post:
            token = live_bridge._get_token()
        assert token == "new-token"
        mock_post.assert_called_once()

    def test_token_within_expiry_buffer_triggers_refresh(self, live_bridge):
        live_bridge._access_token = "old-token"
        live_bridge._token_expires_at = time.monotonic() + 30  # within 60s buffer
        with patch("requests.post", return_value=_token_response("refreshed-token")) as mock_post:
            token = live_bridge._get_token()
        assert token == "refreshed-token"
        mock_post.assert_called_once()

    def test_token_outside_buffer_uses_cache(self, live_bridge):
        live_bridge._access_token = "cached-token"
        live_bridge._token_expires_at = time.monotonic() + 120  # outside 60s buffer
        with patch("requests.post") as mock_post:
            token = live_bridge._get_token()
        assert token == "cached-token"
        mock_post.assert_not_called()

    def test_refresh_failure_returns_none(self, live_bridge):
        with patch("requests.post", side_effect=_make_http_error(401)):
            token = live_bridge._get_token()
        assert token is None

    def test_refresh_failure_clears_cached_token(self, live_bridge):
        live_bridge._access_token = "stale-token"
        with patch("requests.post", side_effect=_make_http_error(401)):
            live_bridge._get_token()
        assert live_bridge._access_token is None

    def test_refresh_sets_expires_at(self, live_bridge):
        before = time.monotonic()
        with patch("requests.post", return_value=_token_response(expires_in=86399)):
            live_bridge._get_token()
        assert live_bridge._token_expires_at > before + 86000

    def test_refresh_uses_client_credentials_grant(self, live_bridge):
        with patch("requests.post", return_value=_token_response()) as mock_post:
            live_bridge._get_token()
        body = mock_post.call_args.kwargs["json"]
        assert body["grant_type"] == "client_credentials"

    def test_refresh_includes_scope(self, live_bridge):
        with patch("requests.post", return_value=_token_response()) as mock_post:
            live_bridge._get_token()
        body = mock_post.call_args.kwargs["json"]
        assert body["scope"] == "write_products,read_products,read_orders"

    def test_refresh_includes_client_id(self, live_bridge):
        with patch("requests.post", return_value=_token_response()) as mock_post:
            live_bridge._get_token()
        body = mock_post.call_args.kwargs["json"]
        assert body["client_id"] == "client-id-123"

    def test_refresh_includes_client_secret(self, live_bridge):
        with patch("requests.post", return_value=_token_response()) as mock_post:
            live_bridge._get_token()
        body = mock_post.call_args.kwargs["json"]
        assert body["client_secret"] == "client-secret-xyz"

    def test_refresh_posts_to_token_endpoint(self, live_bridge):
        with patch("requests.post", return_value=_token_response()) as mock_post:
            live_bridge._get_token()
        url = mock_post.call_args.args[0]
        assert "test-shop.myshopify.com/admin/oauth/access_token" in url


# ---------------------------------------------------------------------------
# publish_product — simulation
# ---------------------------------------------------------------------------

class TestPublishProductSimulation:
    def test_returns_dict(self, bridge):
        result = bridge.publish_product("Report", "desc", 9.99)
        assert isinstance(result, dict)

    def test_simulation_flag_true(self, bridge):
        result = bridge.publish_product("T", "D", 5.0)
        assert result["simulation"] is True

    def test_title_preserved(self, bridge):
        result = bridge.publish_product("My Dataset", "D", 5.0)
        assert result["title"] == "My Dataset"

    def test_price_preserved(self, bridge):
        result = bridge.publish_product("T", "D", 12.50)
        assert result["price"] == pytest.approx(12.50)

    def test_id_has_sim_prefix(self, bridge):
        result = bridge.publish_product("T", "D", 5.0)
        assert result["id"].startswith("sim-")

    def test_unique_ids(self, bridge):
        r1 = bridge.publish_product("T", "D", 5.0)
        r2 = bridge.publish_product("T", "D", 5.0)
        assert r1["id"] != r2["id"]

    def test_no_network_calls(self, bridge):
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            bridge.publish_product("T", "D", 5.0)
            mock_post.assert_not_called()
            mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# publish_product — live mode (POST /admin/api/{version}/products.json)
# ---------------------------------------------------------------------------

class TestPublishProductLive:
    def test_posts_to_products_endpoint(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("T", "D", 9.99)
        url = mock_post.call_args.args[0]
        assert "/products.json" in url

    def test_access_token_in_header(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Shopify-Access-Token"] == "test-token"

    def test_content_type_json(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Content-Type"] == "application/json"

    def test_price_formatted_as_string(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("T", "D", 9.99)
        payload = mock_post.call_args.kwargs["json"]
        variant_price = payload["product"]["variants"][0]["price"]
        assert isinstance(variant_price, str)
        assert variant_price == "9.99"

    def test_title_in_payload(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("My Title", "D", 5.0)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["product"]["title"] == "My Title"

    def test_description_as_body_html(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()) as mock_post:
            live_bridge.publish_product("T", "My Description", 5.0)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["product"]["body_html"] == "My Description"

    def test_returns_product_id_as_string(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response(product_id=999)):
            result = live_bridge.publish_product("T", "D", 5.0)
        assert result["id"] == "999"

    def test_returns_product_url_with_handle(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response(handle="my-handle")):
            result = live_bridge.publish_product("T", "D", 5.0)
        assert result["url"] == "https://test-shop.myshopify.com/products/my-handle"

    def test_simulation_false_on_success(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", return_value=_product_response()):
            result = live_bridge.publish_product("T", "D", 5.0)
        assert result["simulation"] is False

    def test_http_error_falls_back_to_simulation(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", side_effect=_make_http_error(422)):
            result = live_bridge.publish_product("T", "D", 5.0)
        assert result["simulation"] is True

    def test_http_error_does_not_propagate(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.post", side_effect=_make_http_error(500)):
            try:
                live_bridge.publish_product("T", "D", 5.0)
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

    def test_no_token_falls_back_to_simulation(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value=None):
            result = live_bridge.publish_product("T", "D", 5.0)
        assert result["simulation"] is True


# ---------------------------------------------------------------------------
# check_sales — simulation
# ---------------------------------------------------------------------------

class TestCheckSalesSimulation:
    def test_returns_empty_list(self, bridge):
        assert bridge.check_sales("prod-1") == []

    def test_no_network_calls(self, bridge):
        with patch("requests.get") as mock_get:
            bridge.check_sales("pid")
            mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# check_sales — live mode (GET /admin/api/{version}/orders.json)
# ---------------------------------------------------------------------------

class TestCheckSalesLive:
    def test_calls_get_orders_endpoint(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("prod-1")
        url = mock_get.call_args.args[0]
        assert "/orders.json" in url

    def test_access_token_in_header(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("prod-1")
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["X-Shopify-Access-Token"] == "test-token"

    def test_status_any_in_params(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("prod-1")
        params = mock_get.call_args.kwargs["params"]
        assert params["status"] == "any"

    def test_filters_orders_by_product_id(self, live_bridge):
        orders = [
            _order("o-1", "p-match"),
            _order("o-2", "p-other"),
            _order("o-3", "p-match"),
        ]
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-match")
        assert len(result) == 2
        assert all(r["id"] in ("o-1", "o-3") for r in result)

    def test_no_matching_orders_returns_empty(self, live_bridge):
        orders = [_order("o-1", "p-other")]
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-nomatch")
        assert result == []

    def test_converts_total_price_to_float(self, live_bridge):
        orders = [_order("o-1", "p-1", total_price="25.50")]
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-1")
        assert result[0]["total_usd"] == pytest.approx(25.50)

    def test_result_includes_financial_status(self, live_bridge):
        orders = [_order("o-1", "p-1")]
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-1")
        assert result[0]["status"] == "paid"

    def test_http_error_returns_empty_list(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", side_effect=_make_http_error(403)):
            assert live_bridge.check_sales("p-1") == []

    def test_http_error_does_not_propagate(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value="test-token"), \
             patch("requests.get", side_effect=_make_http_error(500)):
            try:
                live_bridge.check_sales("p-1")
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

    def test_no_token_returns_empty_list(self, live_bridge):
        with patch.object(live_bridge, "_get_token", return_value=None):
            assert live_bridge.check_sales("p-1") == []


# ---------------------------------------------------------------------------
# get_market_feedback + record_sale_attempt
# ---------------------------------------------------------------------------

class TestMarketFeedback:
    def test_empty_returns_defaults(self, bridge):
        fb = bridge.get_market_feedback()
        assert fb["avg_price"] == pytest.approx(0.0)
        assert fb["conversion_rate"] == pytest.approx(0.0)
        assert fb["total_attempts"] == 0

    def test_simulation_flag_in_feedback(self, bridge):
        assert bridge.get_market_feedback()["simulation"] is True

    def test_simulation_flag_false_in_live_feedback(self, live_bridge):
        assert live_bridge.get_market_feedback()["simulation"] is False

    def test_all_sold(self, bridge):
        bridge.record_sale_attempt(10.0, sold=True)
        bridge.record_sale_attempt(20.0, sold=True)
        fb = bridge.get_market_feedback()
        assert fb["conversion_rate"] == pytest.approx(1.0)
        assert fb["avg_price"] == pytest.approx(15.0)
        assert fb["total_attempts"] == 2

    def test_none_sold(self, bridge):
        bridge.record_sale_attempt(10.0, sold=False)
        fb = bridge.get_market_feedback()
        assert fb["conversion_rate"] == pytest.approx(0.0)
        assert fb["avg_price"] == pytest.approx(0.0)

    def test_mixed_attempts(self, bridge):
        bridge.record_sale_attempt(10.0, sold=True)
        bridge.record_sale_attempt(20.0, sold=True)
        bridge.record_sale_attempt(15.0, sold=False)
        fb = bridge.get_market_feedback()
        assert fb["total_attempts"] == 3
        assert fb["conversion_rate"] == pytest.approx(2 / 3, abs=1e-3)
        assert fb["avg_price"] == pytest.approx(15.0)

    def test_attempts_accumulate(self, bridge):
        for _ in range(5):
            bridge.record_sale_attempt(5.0, sold=True)
        assert bridge.get_market_feedback()["total_attempts"] == 5
