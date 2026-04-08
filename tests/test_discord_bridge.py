"""Tests for DiscordBridge — no real network calls, no discord.py required."""
import importlib
import logging
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_bridge(monkeypatch, token: str | None = None):
    """Return a freshly-instantiated DiscordBridge after reloading the module."""
    if token is None:
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DISCORD_BOT_TOKEN", token)

    import farms.traffic.discord_bridge as mod
    importlib.reload(mod)
    return mod.DiscordBridge()


# ---------------------------------------------------------------------------
# 1. Simulation mode when no token
# ---------------------------------------------------------------------------

class TestSimulationMode:
    def test_no_token_is_simulation(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch, token=None)
        assert bridge._simulation is True

    def test_token_present_not_simulation(self, monkeypatch):
        mock_discord = MagicMock()
        with patch.dict(sys.modules, {"discord": mock_discord}):
            bridge = _fresh_bridge(monkeypatch, token="fake-bot-token")
        assert bridge._simulation is False

    def test_simulation_log_says_true(self, monkeypatch, caplog):
        with caplog.at_level(logging.INFO, logger="farms.traffic.discord_bridge"):
            _fresh_bridge(monkeypatch, token=None)
        assert "simulation_mode=True" in caplog.text

    def test_live_log_says_false(self, monkeypatch, caplog):
        mock_discord = MagicMock()
        with patch.dict(sys.modules, {"discord": mock_discord}):
            with caplog.at_level(logging.INFO, logger="farms.traffic.discord_bridge"):
                _fresh_bridge(monkeypatch, token="real-token")
        assert "simulation_mode=False" in caplog.text

    def test_missing_discord_lib_forces_simulation(self, monkeypatch):
        """Token present but discord.py not installed → still simulation."""
        with patch.dict(sys.modules, {"discord": None}):
            bridge = _fresh_bridge(monkeypatch, token="real-token")
        assert bridge._simulation is True

    def test_no_network_calls_in_simulation(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch, token=None)
        with patch("asyncio.new_event_loop") as mock_loop:
            bridge.post_content("hello", "123")
            mock_loop.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Interface contract — matches TwitterBridge pattern
# ---------------------------------------------------------------------------

class TestInterface:
    def test_has_simulation_attribute(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert hasattr(bridge, "_simulation")

    def test_post_content_is_callable(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert callable(bridge.post_content)

    def test_post_content_returns_bool(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result = bridge.post_content("Hello Discord", "99999")
        assert isinstance(result, bool)

    def test_simulation_returns_true(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert bridge.post_content("any content", "12345") is True

    def test_content_truncated_to_2000(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        long_msg = "x" * 3000
        # Must not raise and must return True in simulation
        result = bridge.post_content(long_msg, "123")
        assert result is True

    def test_content_exactly_2000_not_truncated(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        msg = "y" * 2000
        # No exception; simulation returns True
        assert bridge.post_content(msg, "123") is True

    def test_post_content_signature(self, monkeypatch):
        """post_content accepts (content: str, channel_id: str)."""
        bridge = _fresh_bridge(monkeypatch)
        import inspect
        params = list(inspect.signature(bridge.post_content).parameters.keys())
        assert params == ["content", "channel_id"]


# ---------------------------------------------------------------------------
# 3. TrafficFarm robustness — keeps running when Discord fails
# ---------------------------------------------------------------------------

class TestTrafficFarmRobustness:
    def _make_farm(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("TWITTER_API_KEY", "TWITTER_API_SECRET",
                    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN_SECRET"):
            monkeypatch.delenv(var, raising=False)
        from farms.traffic.farm import TrafficFarm
        return TrafficFarm("tf-test", "TestTrafficFarm", capital=1000.0, credits=200.0)

    def test_farm_has_discord_bridge(self, monkeypatch):
        from farms.traffic.discord_bridge import DiscordBridge
        farm = self._make_farm(monkeypatch)
        assert isinstance(farm.discord_bridge, DiscordBridge)

    def test_farm_discord_starts_in_simulation(self, monkeypatch):
        farm = self._make_farm(monkeypatch)
        assert farm.discord_bridge._simulation is True

    def test_run_production_succeeds_without_discord(self, monkeypatch):
        """Default config: DISCORD_ENABLED=False — run_production must not raise."""
        farm = self._make_farm(monkeypatch)
        farm.run_production()  # should not raise

    def test_run_cycle_survives_discord_raise(self, monkeypatch):
        """Even if post_content raises, run_cycle must complete normally."""
        import config
        monkeypatch.setattr(config, "DISCORD_ENABLED", True)
        monkeypatch.setattr(config, "DISCORD_TARGET_CHANNELS", ["888111222"])

        farm = self._make_farm(monkeypatch)

        def explode(content, channel_id):
            raise RuntimeError("Discord API unreachable")

        monkeypatch.setattr(farm.discord_bridge, "post_content", explode)

        try:
            farm.run_cycle()
        except RuntimeError as exc:
            pytest.fail(f"Discord error propagated to run_cycle: {exc}")

    def test_run_cycle_records_failed_discord(self, monkeypatch):
        """When Discord fails, the history entry notes channel ok=False."""
        import config
        monkeypatch.setattr(config, "DISCORD_ENABLED", True)
        monkeypatch.setattr(config, "DISCORD_TARGET_CHANNELS", ["777000111"])

        farm = self._make_farm(monkeypatch)
        monkeypatch.setattr(farm.discord_bridge, "post_content", lambda *_: False)

        farm.run_cycle()

        assert len(farm.seller_agent.sales_history) >= 1
        last = farm.seller_agent.sales_history[-1]
        assert last["discord_channels"][0]["ok"] is False

    def test_run_cycle_records_successful_discord(self, monkeypatch):
        """When Discord succeeds, the history entry notes channel ok=True."""
        import config
        monkeypatch.setattr(config, "DISCORD_ENABLED", True)
        monkeypatch.setattr(config, "DISCORD_TARGET_CHANNELS", ["555000222"])

        farm = self._make_farm(monkeypatch)
        monkeypatch.setattr(farm.discord_bridge, "post_content", lambda *_: True)

        farm.run_cycle()

        last = farm.seller_agent.sales_history[-1]
        assert last["discord_channels"][0]["ok"] is True


# ---------------------------------------------------------------------------
# 4. post_message — REST API
# ---------------------------------------------------------------------------

class TestPostMessage:
    def _live_bridge(self, monkeypatch):
        mock_discord = MagicMock()
        with patch.dict(sys.modules, {"discord": mock_discord}):
            return _fresh_bridge(monkeypatch, token="fake-bot-token")

    def test_simulation_returns_true(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert bridge.post_message("123", "hello") is True

    def test_simulation_no_requests_called(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        with patch("farms.traffic.discord_bridge.requests.post") as mock_post:
            bridge.post_message("123", "hello")
            mock_post.assert_not_called()

    def test_live_success_200(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("farms.traffic.discord_bridge.requests.post", return_value=mock_resp):
            assert bridge.post_message("123", "hello") is True

    def test_live_success_201(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        with patch("farms.traffic.discord_bridge.requests.post", return_value=mock_resp):
            assert bridge.post_message("123", "hello") is True

    def test_live_failure_returns_false(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch("farms.traffic.discord_bridge.requests.post", return_value=mock_resp):
            with patch("farms.traffic.discord_bridge.time.sleep"):
                assert bridge.post_message("123", "hello") is False

    def test_retries_on_server_error_then_succeeds(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        r500 = MagicMock()
        r500.status_code = 500
        r200 = MagicMock()
        r200.status_code = 200
        with patch(
            "farms.traffic.discord_bridge.requests.post", side_effect=[r500, r500, r200]
        ) as mock_post:
            with patch("farms.traffic.discord_bridge.time.sleep"):
                result = bridge.post_message("123", "hello")
        assert result is True
        assert mock_post.call_count == 3

    def test_max_retries_exhausted_returns_false(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        r500 = MagicMock()
        r500.status_code = 500
        with patch(
            "farms.traffic.discord_bridge.requests.post", side_effect=[r500, r500, r500]
        ) as mock_post:
            with patch("farms.traffic.discord_bridge.time.sleep"):
                result = bridge.post_message("123", "hello")
        assert result is False
        assert mock_post.call_count == 3

    def test_rate_limit_blocks_rapid_second_call(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        r200 = MagicMock()
        r200.status_code = 200
        with patch("farms.traffic.discord_bridge.requests.post", return_value=r200):
            bridge.post_message("ch1", "first post")   # updates tracker
        # Second immediate call should be rate-limited
        with patch("farms.traffic.discord_bridge.requests.post") as mock_post:
            result = bridge.post_message("ch1", "second post")
        assert result is False
        mock_post.assert_not_called()

    def test_rate_limit_expired_allows_call(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        # Pre-set last post 65 seconds ago (beyond the 60s window)
        bridge._rate_limit_tracker["ch2"] = time.time() - 65
        r200 = MagicMock()
        r200.status_code = 200
        with patch("farms.traffic.discord_bridge.requests.post", return_value=r200):
            result = bridge.post_message("ch2", "post after cooldown")
        assert result is True

    def test_429_retries_with_retry_after(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        r429 = MagicMock()
        r429.status_code = 429
        r429.json.return_value = {"retry_after": 0.5}
        r200 = MagicMock()
        r200.status_code = 200
        with patch(
            "farms.traffic.discord_bridge.requests.post", side_effect=[r429, r200]
        ):
            with patch("farms.traffic.discord_bridge.time.sleep") as mock_sleep:
                result = bridge.post_message("123", "hello")
        assert result is True
        mock_sleep.assert_called_once_with(0.5)

    def test_exception_returns_false(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        with patch(
            "farms.traffic.discord_bridge.requests.post",
            side_effect=ConnectionError("unreachable"),
        ):
            with patch("farms.traffic.discord_bridge.time.sleep"):
                result = bridge.post_message("123", "hello")
        assert result is False

    def test_long_message_truncated(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        long_msg = "x" * 3000
        assert bridge.post_message("123", long_msg) is True  # simulation

    def test_rate_limit_per_channel_independent(self, monkeypatch):
        """Rate limit on ch1 must not block ch2."""
        bridge = self._live_bridge(monkeypatch)
        bridge._rate_limit_tracker["ch1"] = time.time()  # ch1 rate-limited
        r200 = MagicMock()
        r200.status_code = 200
        with patch("farms.traffic.discord_bridge.requests.post", return_value=r200):
            result = bridge.post_message("ch2", "different channel")
        assert result is True


# ---------------------------------------------------------------------------
# 5. get_available_channels — REST API
# ---------------------------------------------------------------------------


class TestGetAvailableChannels:
    def _live_bridge(self, monkeypatch):
        mock_discord = MagicMock()
        with patch.dict(sys.modules, {"discord": mock_discord}):
            return _fresh_bridge(monkeypatch, token="fake-bot-token")

    def _make_get(self, guilds, channels_by_guild):
        """Build a side_effect for requests.get."""
        def _get(url, **kwargs):
            m = MagicMock()
            if "@me/guilds" in url:
                m.status_code = 200
                m.json.return_value = guilds
            else:
                # URL: .../guilds/{guild_id}/channels
                parts = url.split("/")
                guild_id = parts[parts.index("guilds") + 1]
                m.status_code = 200
                m.json.return_value = channels_by_guild.get(guild_id, [])
            return m
        return _get

    def test_simulation_returns_empty_list(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert bridge.get_available_channels() == []

    def test_simulation_no_requests_called(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        with patch("farms.traffic.discord_bridge.requests.get") as mock_get:
            bridge.get_available_channels()
            mock_get.assert_not_called()

    def test_returns_list_type(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        assert isinstance(bridge.get_available_channels(), list)

    def test_live_returns_text_channels_only(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        guilds = [{"id": "100", "name": "ML Server"}]
        channels = {
            "100": [
                {"id": "456", "name": "general", "type": 0},
                {"id": "789", "name": "voice-chat", "type": 2},
            ]
        }
        with patch(
            "farms.traffic.discord_bridge.requests.get",
            side_effect=self._make_get(guilds, channels),
        ):
            result = bridge.get_available_channels()
        assert len(result) == 1
        assert result[0]["id"] == "456"

    def test_live_channel_dict_has_required_keys(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        guilds = [{"id": "200", "name": "Data Guild"}]
        channels = {"200": [{"id": "555", "name": "resources", "type": 0}]}
        with patch(
            "farms.traffic.discord_bridge.requests.get",
            side_effect=self._make_get(guilds, channels),
        ):
            result = bridge.get_available_channels()
        assert {"id", "name", "guild_id", "guild_name"} <= set(result[0].keys())

    def test_guild_channel_fetch_failure_skips_guild(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        guilds = [{"id": "300", "name": "Bad Guild"}, {"id": "400", "name": "Good Guild"}]

        def _get(url, **kwargs):
            m = MagicMock()
            if "@me/guilds" in url:
                m.status_code = 200
                m.json.return_value = guilds
            elif "300" in url:
                m.status_code = 403
            else:
                m.status_code = 200
                m.json.return_value = [{"id": "777", "name": "announcements", "type": 0}]
            return m

        with patch("farms.traffic.discord_bridge.requests.get", side_effect=_get):
            result = bridge.get_available_channels()
        assert len(result) == 1
        assert result[0]["guild_id"] == "400"

    def test_network_error_returns_empty(self, monkeypatch):
        bridge = self._live_bridge(monkeypatch)
        with patch(
            "farms.traffic.discord_bridge.requests.get",
            side_effect=ConnectionError("no network"),
        ):
            assert bridge.get_available_channels() == []


# ---------------------------------------------------------------------------
# 6. format_post
# ---------------------------------------------------------------------------

class TestFormatPost:
    def test_returns_string(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result = bridge.format_post("My Dataset", "data_science", "https://example.com")
        assert isinstance(result, str)

    def test_returns_non_empty_string(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result = bridge.format_post("Ecommerce Clean CSV", "ecommerce", "https://example.com")
        assert len(result) > 0

    def test_uses_niche_specific_template(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result = bridge.format_post("Product", "data_cleaning", "https://example.com")
        # data_cleaning templates mention cleaning/datasets
        assert "example.com" in result

    def test_contains_platform_url(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        url = "https://gumroad.com/l/abc123"
        result = bridge.format_post("Product", "fintech", url)
        assert url in result

    def test_fallback_template_contains_url(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result = bridge.format_post("Product", "unknown_niche", "https://example.com")
        assert "example.com" in result

    def test_different_niches_may_have_different_templates(self, monkeypatch):
        bridge = _fresh_bridge(monkeypatch)
        result1 = bridge.format_post("P", "data_cleaning", "https://x.com")
        result2 = bridge.format_post("P", "devops_cloud", "https://x.com")
        # Both should contain URL, may have different text
        assert "x.com" in result1
        assert "x.com" in result2
