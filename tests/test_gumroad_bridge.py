"""Tests for GumroadRevenueBridge — no real network calls."""
import pytest
from unittest.mock import MagicMock, patch

from requests import HTTPError

from farms.gumroad_bridge import GumroadRevenueBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_error(status_code: int) -> HTTPError:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return HTTPError(response=mock_resp)


def _product_response(
    product_id: str = "fpwkdg",
    short_url: str = "https://app.gumroad.com/l/fpwkdg",
) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {
        "success": True,
        "product": {
            "id": product_id,
            "name": "Test Product",
            "short_url": short_url,
            "price": 999,
        },
    }
    return mock


def _sales_response(sales: list[dict] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {
        "success": True,
        "sales": sales or [],
    }
    return mock


def _sale(
    sale_id: str = "s-1",
    price: int = 999,
    refunded: bool = False,
    chargebacked: bool = False,
) -> dict:
    return {
        "id": sale_id,
        "price": price,
        "refunded": refunded,
        "chargebacked": chargebacked,
        "created_at": "2026-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge(monkeypatch):
    """No token -> simulation mode (env var cleared so it never leaks in)."""
    monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)
    return GumroadRevenueBridge()


@pytest.fixture
def live_bridge():
    """Token supplied directly — no env required."""
    return GumroadRevenueBridge(access_token="test-token")


@pytest.fixture
def live_bridge_with_product():
    """Live bridge with a pre-existing product_id."""
    return GumroadRevenueBridge(access_token="test-token", product_id="fpwkdg")


# ---------------------------------------------------------------------------
# Simulation mode detection
# ---------------------------------------------------------------------------

class TestSimulationMode:
    def test_no_token_is_simulation(self, bridge):
        assert bridge._simulation is True

    def test_token_present_is_not_simulation(self, live_bridge):
        assert live_bridge._simulation is False

    def test_env_var_activates_live_mode(self, monkeypatch):
        monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "env-token")
        b = GumroadRevenueBridge()
        assert b._simulation is False

    def test_env_var_absent_stays_simulation(self, monkeypatch):
        monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)
        b = GumroadRevenueBridge()
        assert b._simulation is True

    def test_product_id_stored(self):
        b = GumroadRevenueBridge(access_token="tok", product_id="abc123")
        assert b.product_id == "abc123"

    def test_token_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "env-tok")
        b = GumroadRevenueBridge()
        assert b.access_token == "env-tok"

    def test_no_product_id_by_default(self, live_bridge):
        assert live_bridge.product_id is None


# ---------------------------------------------------------------------------
# publish_product — simulation
# ---------------------------------------------------------------------------

class TestPublishProductSimulation:
    def test_returns_dict(self, bridge):
        assert isinstance(bridge.publish_product("T", "D", 9.99), dict)

    def test_simulation_flag_true(self, bridge):
        assert bridge.publish_product("T", "D", 9.99)["simulation"] is True

    def test_title_preserved(self, bridge):
        assert bridge.publish_product("My Report", "D", 9.99)["title"] == "My Report"

    def test_price_preserved(self, bridge):
        result = bridge.publish_product("T", "D", 12.50)
        assert result["price"] == pytest.approx(12.50)

    def test_id_has_sim_prefix(self, bridge):
        assert bridge.publish_product("T", "D", 5.0)["id"].startswith("sim-")

    def test_unique_ids(self, bridge):
        r1 = bridge.publish_product("T", "D", 5.0)
        r2 = bridge.publish_product("T", "D", 5.0)
        assert r1["id"] != r2["id"]

    def test_no_network_calls(self, bridge):
        with patch("requests.post") as mock_post, patch("requests.put") as mock_put:
            bridge.publish_product("T", "D", 5.0)
            mock_post.assert_not_called()
            mock_put.assert_not_called()


# ---------------------------------------------------------------------------
# publish_product — live mode, no product_id
# Gumroad has no create endpoint: always simulates even with a valid token.
# ---------------------------------------------------------------------------

class TestPublishProductNoProductId:
    def test_simulation_flag_true_even_with_token(self, live_bridge):
        result = live_bridge.publish_product("T", "D", 9.99)
        assert result["simulation"] is True

    def test_no_post_call(self, live_bridge):
        with patch("requests.post") as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
            mock_post.assert_not_called()

    def test_no_put_call(self, live_bridge):
        with patch("requests.put") as mock_put:
            live_bridge.publish_product("T", "D", 5.0)
            mock_put.assert_not_called()

    def test_title_preserved(self, live_bridge):
        assert live_bridge.publish_product("My Title", "D", 5.0)["title"] == "My Title"

    def test_price_preserved(self, live_bridge):
        result = live_bridge.publish_product("T", "D", 12.50)
        assert result["price"] == pytest.approx(12.50)

    def test_id_has_sim_prefix(self, live_bridge):
        assert live_bridge.publish_product("T", "D", 5.0)["id"].startswith("sim-")


# ---------------------------------------------------------------------------
# publish_product — live mode, with product_id (PUT /v2/products/:id)
# ---------------------------------------------------------------------------

class TestPublishProductUpdate:
    def test_sends_put_not_post(self, live_bridge_with_product):
        with patch("requests.put", return_value=_product_response()) as mock_put, \
             patch("requests.post") as mock_post:
            live_bridge_with_product.publish_product("T", "D", 9.99)
        mock_put.assert_called_once()
        mock_post.assert_not_called()

    def test_put_url_contains_product_id(self, live_bridge_with_product):
        with patch("requests.put", return_value=_product_response()) as mock_put:
            live_bridge_with_product.publish_product("T", "D", 9.99)
        url = mock_put.call_args.args[0]
        assert "fpwkdg" in url

    def test_price_sent_as_cents(self, live_bridge_with_product):
        with patch("requests.put", return_value=_product_response()) as mock_put:
            live_bridge_with_product.publish_product("T", "D", 15.00)
        assert mock_put.call_args.kwargs["data"]["price"] == 1500

    def test_returns_product_id(self, live_bridge_with_product):
        with patch("requests.put", return_value=_product_response(product_id="fpwkdg")):
            result = live_bridge_with_product.publish_product("T", "D", 5.0)
        assert result["id"] == "fpwkdg"

    def test_simulation_false_on_success(self, live_bridge_with_product):
        with patch("requests.put", return_value=_product_response()):
            result = live_bridge_with_product.publish_product("T", "D", 5.0)
        assert result["simulation"] is False

    def test_http_error_falls_back_to_simulation(self, live_bridge_with_product):
        with patch("requests.put", side_effect=_make_http_error(404)):
            result = live_bridge_with_product.publish_product("T", "D", 5.0)
        assert result["simulation"] is True


# ---------------------------------------------------------------------------
# check_sales — simulation
# ---------------------------------------------------------------------------

class TestCheckSalesSimulation:
    def test_returns_empty_list(self, bridge):
        assert bridge.check_sales("fpwkdg") == []

    def test_no_network_calls(self, bridge):
        with patch("requests.get") as mock_get:
            bridge.check_sales("fpwkdg")
            mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# check_sales — live mode (GET /v2/products/:id/sales)
# ---------------------------------------------------------------------------

class TestCheckSalesLive:
    def test_gets_sales_endpoint(self, live_bridge):
        with patch("requests.get", return_value=_sales_response()) as mock_get:
            live_bridge.check_sales("fpwkdg")
        url = mock_get.call_args.args[0]
        assert "fpwkdg/sales" in url

    def test_authorization_header(self, live_bridge):
        with patch("requests.get", return_value=_sales_response()) as mock_get:
            live_bridge.check_sales("fpwkdg")
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-token"

    def test_converts_price_cents_to_usd(self, live_bridge):
        sales = [_sale(price=999)]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert result[0]["total_usd"] == pytest.approx(9.99)

    def test_status_paid_for_normal_sale(self, live_bridge):
        sales = [_sale(refunded=False, chargebacked=False)]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert result[0]["status"] == "paid"

    def test_status_refunded(self, live_bridge):
        sales = [_sale(refunded=True)]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert result[0]["status"] == "refunded"

    def test_status_chargebacked(self, live_bridge):
        sales = [_sale(chargebacked=True)]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert result[0]["status"] == "chargebacked"

    def test_includes_created_at(self, live_bridge):
        sales = [_sale()]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert result[0]["created_at"] == "2026-01-01T00:00:00Z"

    def test_multiple_sales_returned(self, live_bridge):
        sales = [_sale("s-1"), _sale("s-2"), _sale("s-3")]
        with patch("requests.get", return_value=_sales_response(sales)):
            result = live_bridge.check_sales("fpwkdg")
        assert len(result) == 3

    def test_empty_sales_returns_empty_list(self, live_bridge):
        with patch("requests.get", return_value=_sales_response([])):
            result = live_bridge.check_sales("fpwkdg")
        assert result == []

    def test_http_error_returns_empty_list(self, live_bridge):
        with patch("requests.get", side_effect=_make_http_error(403)):
            assert live_bridge.check_sales("fpwkdg") == []

    def test_http_error_does_not_propagate(self, live_bridge):
        with patch("requests.get", side_effect=_make_http_error(500)):
            try:
                live_bridge.check_sales("fpwkdg")
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

    def test_api_success_false_returns_empty_list(self, live_bridge):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": False}
        with patch("requests.get", return_value=mock_resp):
            assert live_bridge.check_sales("fpwkdg") == []


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
