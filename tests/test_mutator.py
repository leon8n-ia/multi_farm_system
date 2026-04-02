import os
import pytest
from unittest.mock import MagicMock, patch

from config import COST_MUTATION, INITIAL_CREDITS
from mutation.claude_mutator import (
    STRING_CHOICES,
    CostCircuitBreaker,
    ESTIMATED_COST_PER_CALL,
    mutate_strategy,
    random_mutate,
)
from shared.models import Agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_STRATEGY = {
    "primary_channel": "gumroad",
    "pricing_model": "fixed",
    "base_price": 12.0,
    "discount_threshold": 3,
    "discount_rate": 0.20,
    "listing_quality": "high",
    "target_audience": "developers",
    "bundle_strategy": False,
}


def make_agent(strategy: dict | None = None) -> Agent:
    return Agent(
        id="test-agent",
        credits=float(INITIAL_CREDITS),
        strategy=dict(strategy or BASE_STRATEGY),
    )


# ---------------------------------------------------------------------------
# random_mutate
# ---------------------------------------------------------------------------

class TestRandomMutate:
    def test_returns_dict(self):
        assert isinstance(random_mutate(BASE_STRATEGY), dict)

    def test_returns_same_keys(self):
        result = random_mutate(BASE_STRATEGY)
        assert set(result.keys()) == set(BASE_STRATEGY.keys())

    def test_original_not_modified(self):
        original = dict(BASE_STRATEGY)
        random_mutate(original)
        assert original == BASE_STRATEGY

    def test_empty_strategy_returned_unchanged(self):
        assert random_mutate({}) == {}

    def test_bool_only_strategy_returned_unchanged(self):
        strategy = {"bundle_strategy": False, "active": True}
        assert random_mutate(strategy) == strategy

    def test_float_mutation_within_20_percent(self):
        strategy = {"base_price": 12.0}
        for _ in range(60):
            result = random_mutate(strategy)
            assert 12.0 * 0.8 <= result["base_price"] <= 12.0 * 1.2 + 1e-9

    def test_float_mutation_stays_positive(self):
        strategy = {"base_price": 0.01}
        for _ in range(30):
            assert random_mutate(strategy)["base_price"] >= 0.01

    def test_int_mutation_within_20_percent(self):
        strategy = {"discount_threshold": 10}
        for _ in range(60):
            result = random_mutate(strategy)
            assert 8 <= result["discount_threshold"] <= 12

    def test_int_mutation_stays_positive(self):
        strategy = {"discount_threshold": 1}
        for _ in range(30):
            assert random_mutate(strategy)["discount_threshold"] >= 1

    def test_string_mutated_to_valid_choice(self):
        strategy = {"primary_channel": "gumroad"}
        for _ in range(20):
            result = random_mutate(strategy)
            assert result["primary_channel"] in STRING_CHOICES["primary_channel"]

    def test_unknown_string_key_not_mutated(self):
        strategy = {"custom_field": "some_value"}
        for _ in range(20):
            assert random_mutate(strategy)["custom_field"] == "some_value"

    def test_mutates_at_most_two_keys(self):
        strategy = {
            "base_price": 12.0,
            "discount_rate": 0.20,
            "base_extra": 5.0,
        }
        changed_counts = []
        for _ in range(50):
            result = random_mutate(strategy)
            changed = sum(1 for k in strategy if result[k] != strategy[k])
            changed_counts.append(changed)
        assert all(c <= 2 for c in changed_counts)


# ---------------------------------------------------------------------------
# CostCircuitBreaker
# ---------------------------------------------------------------------------

class TestCostCircuitBreaker:
    def test_allows_below_cycle_limit(self):
        cb = CostCircuitBreaker()
        assert cb.can_proceed(0.001) is True

    def test_allows_exactly_at_cycle_limit(self):
        cb = CostCircuitBreaker()
        assert cb.can_proceed(CostCircuitBreaker.MAX_API_COST_PER_CYCLE) is True

    def test_blocks_when_cycle_limit_exceeded(self):
        cb = CostCircuitBreaker()
        cb.cycle_cost = CostCircuitBreaker.MAX_API_COST_PER_CYCLE
        assert cb.can_proceed(0.001) is False

    def test_blocks_when_daily_limit_exceeded(self):
        cb = CostCircuitBreaker()
        cb.daily_cost = CostCircuitBreaker.MAX_DAILY_COST
        assert cb.can_proceed(0.001) is False

    def test_blocks_when_both_limits_exceeded(self):
        cb = CostCircuitBreaker()
        cb.cycle_cost = CostCircuitBreaker.MAX_API_COST_PER_CYCLE
        cb.daily_cost = CostCircuitBreaker.MAX_DAILY_COST
        assert cb.can_proceed(0.001) is False

    def test_record_spend_updates_cycle_cost(self):
        cb = CostCircuitBreaker()
        cb.record_spend(1.0)
        assert cb.cycle_cost == pytest.approx(1.0)

    def test_record_spend_updates_daily_cost(self):
        cb = CostCircuitBreaker()
        cb.record_spend(1.0)
        assert cb.daily_cost == pytest.approx(1.0)

    def test_reset_cycle_clears_cycle_cost(self):
        cb = CostCircuitBreaker()
        cb.record_spend(1.5)
        cb.reset_cycle()
        assert cb.cycle_cost == 0.0

    def test_reset_cycle_preserves_daily_cost(self):
        cb = CostCircuitBreaker()
        cb.record_spend(1.5)
        cb.reset_cycle()
        assert cb.daily_cost == pytest.approx(1.5)

    def test_multiple_spends_accumulate(self):
        cb = CostCircuitBreaker()
        cb.record_spend(0.5)
        cb.record_spend(0.5)
        assert cb.cycle_cost == pytest.approx(1.0)
        assert cb.daily_cost == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# mutate_strategy
# ---------------------------------------------------------------------------

class TestMutateStrategy:
    def test_fallback_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        agent = make_agent()
        cb = CostCircuitBreaker()

        with patch("mutation.claude_mutator._call_claude_api") as mock_api:
            result = mutate_strategy(agent, {}, circuit_breaker=cb)
            mock_api.assert_not_called()

        assert set(result.keys()) == set(BASE_STRATEGY.keys())

    def test_fallback_when_circuit_breaker_blocks(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        cb = CostCircuitBreaker()
        cb.cycle_cost = CostCircuitBreaker.MAX_API_COST_PER_CYCLE  # exhaust budget

        with patch("mutation.claude_mutator._call_claude_api") as mock_api:
            result = mutate_strategy(make_agent(), {}, circuit_breaker=cb)
            mock_api.assert_not_called()

        assert set(result.keys()) == set(BASE_STRATEGY.keys())

    def test_fallback_when_api_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        cb = CostCircuitBreaker()

        with patch(
            "mutation.claude_mutator._call_claude_api",
            side_effect=Exception("network error"),
        ):
            result = mutate_strategy(make_agent(), {}, circuit_breaker=cb)

        assert set(result.keys()) == set(BASE_STRATEGY.keys())

    def test_deducts_cost_mutation_on_fallback(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        agent = make_agent()
        credits_before = agent.credits
        mutate_strategy(agent, {})
        assert agent.credits == pytest.approx(credits_before - COST_MUTATION)

    def test_deducts_cost_mutation_on_api_success(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        agent = make_agent()
        credits_before = agent.credits
        new_strat = dict(BASE_STRATEGY)

        with patch("mutation.claude_mutator._call_claude_api", return_value=new_strat):
            mutate_strategy(agent, {})

        assert agent.credits == pytest.approx(credits_before - COST_MUTATION)

    def test_updates_agent_strategy(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        agent = make_agent({"base_price": 12.0})
        mutate_strategy(agent, {})
        assert agent.strategy is not None
        assert "base_price" in agent.strategy

    def test_api_result_applied_to_agent(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        agent = make_agent()
        new_strat = {**BASE_STRATEGY, "base_price": 25.0}

        with patch("mutation.claude_mutator._call_claude_api", return_value=new_strat):
            result = mutate_strategy(agent, {})

        assert result["base_price"] == pytest.approx(25.0)
        assert agent.strategy["base_price"] == pytest.approx(25.0)

    def test_api_called_when_key_and_budget_available(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        cb = CostCircuitBreaker()
        agent = make_agent()

        with patch(
            "mutation.claude_mutator._call_claude_api",
            return_value=dict(BASE_STRATEGY),
        ) as mock_api:
            mutate_strategy(agent, {"profit": 100}, circuit_breaker=cb)
            mock_api.assert_called_once()

    def test_circuit_breaker_spend_recorded_on_api_success(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-key")
        cb = CostCircuitBreaker()

        with patch(
            "mutation.claude_mutator._call_claude_api",
            return_value=dict(BASE_STRATEGY),
        ):
            mutate_strategy(make_agent(), {}, circuit_breaker=cb)

        assert cb.cycle_cost == pytest.approx(ESTIMATED_COST_PER_CALL)

    def test_circuit_breaker_not_charged_on_fallback(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cb = CostCircuitBreaker()
        mutate_strategy(make_agent(), {}, circuit_breaker=cb)
        assert cb.cycle_cost == 0.0
