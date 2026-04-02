"""Tests for LemonSqueezyRevenueBridge — no real network calls."""
import pytest
from unittest.mock import MagicMock, call, patch

from requests import HTTPError

from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_error(status_code: int) -> HTTPError:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return HTTPError(response=mock_resp)


def _checkout_response(checkout_id: str = "co-abc123", url: str = "https://buy.ls/abc") -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {
        "data": {
            "type": "checkouts",
            "id": checkout_id,
            "attributes": {"url": url, "custom_price": 999},
        }
    }
    return mock


def _orders_response(orders: list[dict] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"data": orders or []}
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bridge():
    """No token → simulation mode."""
    return LemonSqueezyRevenueBridge()


@pytest.fixture
def live_bridge():
    """Full credentials supplied directly — no env required."""
    return LemonSqueezyRevenueBridge(
        api_token="test-token-xyz",
        store_id="42",
        variant_id="v-99",
    )


# ---------------------------------------------------------------------------
# Simulation mode detection
# ---------------------------------------------------------------------------

class TestSimulationMode:
    def test_no_token_is_simulation(self, bridge):
        assert bridge._simulation is True

    def test_explicit_token_not_simulation(self, live_bridge):
        assert live_bridge._simulation is False

    def test_env_token_activates_live_mode(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_TOKEN", "env-token")
        b = LemonSqueezyRevenueBridge()
        assert b._simulation is False

    def test_no_env_token_stays_simulation(self, monkeypatch):
        monkeypatch.delenv("LEMONSQUEEZY_API_TOKEN", raising=False)
        b = LemonSqueezyRevenueBridge()
        assert b._simulation is True

    def test_store_id_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_TOKEN", "t")
        monkeypatch.setenv("LEMONSQUEEZY_STORE_ID", "77")
        b = LemonSqueezyRevenueBridge()
        assert b.store_id == "77"

    def test_variant_id_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("LEMONSQUEEZY_API_TOKEN", "t")
        monkeypatch.setenv("LEMONSQUEEZY_VARIANT_ID", "v-55")
        b = LemonSqueezyRevenueBridge()
        assert b.variant_id == "v-55"


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

    def test_no_store_id_also_simulates(self):
        b = LemonSqueezyRevenueBridge(api_token="t", store_id=None)
        result = b.publish_product("T", "D", 5.0)
        assert result["simulation"] is True


# ---------------------------------------------------------------------------
# publish_product — live mode (POST /v1/checkouts)
# ---------------------------------------------------------------------------

class TestPublishProductLive:
    def test_calls_post_checkouts(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 9.99)
            mock_post.assert_called_once()
            url = mock_post.call_args.args[0]
            assert url.endswith("/checkouts")

    def test_bearer_auth_header(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
            headers = mock_post.call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer test-token-xyz"

    def test_json_api_content_type(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
            headers = mock_post.call_args.kwargs["headers"]
            assert headers["Content-Type"] == "application/vnd.api+json"

    def test_price_sent_as_cents(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 9.99)
            payload = mock_post.call_args.kwargs["json"]
            sent_price = payload["data"]["attributes"]["custom_price"]
            assert sent_price == 999

    def test_payload_has_store_relationship(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
            rels = mock_post.call_args.kwargs["json"]["data"]["relationships"]
            assert rels["store"]["data"]["id"] == "42"

    def test_payload_has_variant_relationship(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("T", "D", 5.0)
            rels = mock_post.call_args.kwargs["json"]["data"]["relationships"]
            assert rels["variant"]["data"]["id"] == "v-99"

    def test_title_in_product_options(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post:
            live_bridge.publish_product("My Title", "My Desc", 5.0)
            attrs = mock_post.call_args.kwargs["json"]["data"]["attributes"]
            assert attrs["product_options"]["name"] == "My Title"

    def test_returns_checkout_id(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response("co-xyz")):
            result = live_bridge.publish_product("T", "D", 5.0)
            assert result["id"] == "co-xyz"

    def test_returns_checkout_url(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response(url="https://buy.ls/test")):
            result = live_bridge.publish_product("T", "D", 5.0)
            assert result["url"] == "https://buy.ls/test"

    def test_simulation_false_on_success(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()):
            result = live_bridge.publish_product("T", "D", 5.0)
            assert result["simulation"] is False

    def test_http_error_falls_back_to_simulation(self, live_bridge):
        with patch("requests.post", side_effect=_make_http_error(422)):
            result = live_bridge.publish_product("T", "D", 5.0)
            assert result["simulation"] is True

    def test_http_error_does_not_propagate(self, live_bridge):
        with patch("requests.post", side_effect=_make_http_error(500)):
            try:
                live_bridge.publish_product("T", "D", 5.0)
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")

    def test_no_variant_id_falls_back_to_simulation(self):
        b = LemonSqueezyRevenueBridge(api_token="t", store_id="1", variant_id=None)
        with patch.object(b, "_discover_variant_id", return_value=None):
            result = b.publish_product("T", "D", 5.0)
        assert result["simulation"] is True


# ---------------------------------------------------------------------------
# publish_product — variant auto-discovery
# ---------------------------------------------------------------------------

class TestVariantDiscovery:
    def _make_products_resp(self, product_id: str) -> MagicMock:
        m = MagicMock()
        m.json.return_value = {"data": [{"id": product_id, "type": "products"}]}
        return m

    def _make_variants_resp(self, variant_id: str) -> MagicMock:
        m = MagicMock()
        m.json.return_value = {"data": [{"id": variant_id, "type": "variants"}]}
        return m

    def test_discover_variant_used_when_none_set(self):
        b = LemonSqueezyRevenueBridge(api_token="t", store_id="1", variant_id=None)
        get_responses = [self._make_products_resp("p-1"), self._make_variants_resp("v-auto")]

        def get_side_effect(url, **kwargs):
            return get_responses.pop(0)

        with patch("requests.get", side_effect=get_side_effect), \
             patch("requests.post", return_value=_checkout_response()) as mock_post:
            b.publish_product("T", "D", 5.0)
            rels = mock_post.call_args.kwargs["json"]["data"]["relationships"]
            assert rels["variant"]["data"]["id"] == "v-auto"

    def test_explicit_variant_skips_discovery(self, live_bridge):
        with patch("requests.post", return_value=_checkout_response()) as mock_post, \
             patch("requests.get") as mock_get:
            live_bridge.publish_product("T", "D", 5.0)
            # GET should NOT be called for variant discovery
            mock_get.assert_not_called()


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
# check_sales — live mode (GET /v1/orders)
# ---------------------------------------------------------------------------

class TestCheckSalesLive:
    def _order(self, order_id: str, product_id: str, total_usd: int = 1000) -> dict:
        """Build a minimal order data object."""
        return {
            "id": order_id,
            "type": "orders",
            "attributes": {
                "status": "paid",
                "total_usd": total_usd,
                "created_at": "2025-01-01T00:00:00Z",
                "first_order_item": {"product_id": product_id},
            },
        }

    def test_calls_get_orders_endpoint(self, live_bridge):
        with patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("p-1")
            url = mock_get.call_args.args[0]
            assert url.endswith("/orders")

    def test_bearer_auth_header(self, live_bridge):
        with patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("p-1")
            headers = mock_get.call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer test-token-xyz"

    def test_store_id_in_filter_params(self, live_bridge):
        with patch("requests.get", return_value=_orders_response()) as mock_get:
            live_bridge.check_sales("p-1")
            params = mock_get.call_args.kwargs["params"]
            assert params["filter[store_id]"] == "42"

    def test_filters_orders_by_product_id(self, live_bridge):
        orders = [
            self._order("o-1", "p-match"),
            self._order("o-2", "p-other"),
            self._order("o-3", "p-match"),
        ]
        with patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-match")
        assert len(result) == 2
        assert all(r["id"] in ("o-1", "o-3") for r in result)

    def test_converts_total_usd_to_dollars(self, live_bridge):
        orders = [self._order("o-1", "p-1", total_usd=2500)]
        with patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-1")
        assert result[0]["total_usd"] == pytest.approx(25.0)

    def test_no_matching_orders_returns_empty(self, live_bridge):
        orders = [self._order("o-1", "p-other")]
        with patch("requests.get", return_value=_orders_response(orders)):
            result = live_bridge.check_sales("p-nomatch")
        assert result == []

    def test_http_error_returns_empty_list(self, live_bridge):
        with patch("requests.get", side_effect=_make_http_error(404)):
            assert live_bridge.check_sales("p-1") == []

    def test_http_error_does_not_propagate(self, live_bridge):
        with patch("requests.get", side_effect=_make_http_error(500)):
            try:
                live_bridge.check_sales("p-1")
            except Exception as exc:
                pytest.fail(f"Exception propagated: {exc}")


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


# ---------------------------------------------------------------------------
# Farm integration
# ---------------------------------------------------------------------------

class TestFarmIntegration:
    def test_farm_has_revenue_bridge(self, tmp_path):
        from farms.data_cleaning.farm import DataCleaningFarm
        from farms.revenue_bridge_router import RevenueBridgeRouter
        p = tmp_path / "data.csv"
        p.write_text("name\nalice\n")
        farm = DataCleaningFarm("f1", "Farm 1", capital=1000.0, credits=200.0, input_path=str(p))
        assert isinstance(farm.revenue_bridge, RevenueBridgeRouter)

    def test_farm_bridge_has_lemonsqueezy_as_first_bridge(self, tmp_path, monkeypatch):
        from farms.data_cleaning.farm import DataCleaningFarm
        monkeypatch.delenv("LEMONSQUEEZY_API_TOKEN", raising=False)
        p = tmp_path / "data.csv"
        p.write_text("name\nalice\n")
        farm = DataCleaningFarm("f1", "Farm 1", capital=1000.0, credits=200.0, input_path=str(p))
        assert isinstance(farm.revenue_bridge._bridges[0], LemonSqueezyRevenueBridge)

    def test_build_farm_context_includes_market_feedback(self, tmp_path):
        from farms.data_cleaning.farm import DataCleaningFarm
        p = tmp_path / "data.csv"
        p.write_text("name\nalice\n")
        farm = DataCleaningFarm("f1", "Farm 1", capital=1000.0, credits=200.0, input_path=str(p))
        ctx = farm.build_farm_context()
        assert "market_feedback" in ctx
        assert isinstance(ctx["market_feedback"], dict)

    def test_run_sales_records_attempts(self, tmp_path):
        from farms.data_cleaning.farm import DataCleaningFarm
        from farms.data_cleaning.producer_agent import ProducerAgent
        from shared.models import Agent
        p = tmp_path / "data.csv"
        p.write_text("name\nalice\nbob\nalice\n")
        farm = DataCleaningFarm("f1", "Farm 1", capital=1000.0, credits=500.0, input_path=str(p))
        farm.producer_agents.append(ProducerAgent(Agent(id="pa-0", credits=200.0)))
        farm.run_production()
        farm.run_competition()
        farm.run_sales()
        assert len(farm.revenue_bridge._attempts) >= 1
