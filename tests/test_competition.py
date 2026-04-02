import pytest

from config import NO_PROFIT_THRESHOLD, PENALTY_LOSER, REWARD_WINNER
from core.competition import calculate_agent_score, run_competition
from core.economy import EconomyEngine
from shared.models import Agent


INITIAL = 200.0


def make_agent(id, *, quality=0.0, speed=0.0, consistency=0.0,
               resource_efficiency=0.0, sold=False, cycles_without_profit=0):
    a = Agent(id=id, credits=INITIAL)
    a.quality = quality
    a.speed = speed
    a.consistency = consistency
    a.resource_efficiency = resource_efficiency
    a.sold = sold
    a.cycles_without_profit = cycles_without_profit
    return a


# ---------------------------------------------------------------------------
# calculate_agent_score
# ---------------------------------------------------------------------------

class TestCalculateAgentScore:
    def test_quality_weight_40pct(self):
        a = make_agent("a", quality=100)
        assert calculate_agent_score(a) == pytest.approx(40.0)

    def test_speed_weight_20pct(self):
        a = make_agent("a", speed=100)
        assert calculate_agent_score(a) == pytest.approx(20.0)

    def test_consistency_weight_20pct(self):
        a = make_agent("a", consistency=100)
        assert calculate_agent_score(a) == pytest.approx(20.0)

    def test_resource_efficiency_weight_20pct(self):
        a = make_agent("a", resource_efficiency=100)
        assert calculate_agent_score(a) == pytest.approx(20.0)

    def test_all_weights_sum_to_100(self):
        a = make_agent("a", quality=100, speed=100, consistency=100, resource_efficiency=100)
        assert calculate_agent_score(a) == pytest.approx(100.0)

    def test_sold_boost_adds_100(self):
        a = make_agent("a", sold=True)
        assert calculate_agent_score(a) == pytest.approx(100.0)

    def test_sold_boost_stacks_with_metrics(self):
        a = make_agent("a", quality=100, speed=100, consistency=100,
                       resource_efficiency=100, sold=True)
        assert calculate_agent_score(a) == pytest.approx(200.0)

    def test_no_sold_no_boost(self):
        a = make_agent("a", quality=50)
        assert calculate_agent_score(a) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# run_competition — 3 agent mock scenarios
# ---------------------------------------------------------------------------

class TestRunCompetition:
    def setup_method(self):
        self.economy = EconomyEngine()
        # agent_a has highest score → winner
        self.agent_a = make_agent("a", quality=80, speed=80, consistency=80, resource_efficiency=80)
        # agent_b mid score
        self.agent_b = make_agent("b", quality=50, speed=50, consistency=50, resource_efficiency=50)
        # agent_c lowest score
        self.agent_c = make_agent("c", quality=10, speed=10, consistency=10, resource_efficiency=10)
        self.agents = [self.agent_a, self.agent_b, self.agent_c]

    def test_returns_winner(self):
        winner = run_competition(self.agents, self.economy)
        assert winner is self.agent_a

    def test_winner_receives_reward(self):
        run_competition(self.agents, self.economy)
        assert self.agent_a.credits == INITIAL + REWARD_WINNER

    def test_losers_receive_penalty(self):
        run_competition(self.agents, self.economy)
        assert self.agent_b.credits == INITIAL - PENALTY_LOSER
        assert self.agent_c.credits == INITIAL - PENALTY_LOSER

    def test_empty_agents_raises(self):
        with pytest.raises(ValueError):
            run_competition([], self.economy)

    def test_single_agent_wins(self):
        solo = make_agent("solo", quality=10)
        winner = run_competition([solo], self.economy)
        assert winner is solo
        assert solo.credits == INITIAL + REWARD_WINNER


# ---------------------------------------------------------------------------
# Temporal pressure
# ---------------------------------------------------------------------------

class TestTemporalPressure:
    def setup_method(self):
        self.economy = EconomyEngine()

    def test_no_pressure_below_threshold(self):
        agent = make_agent("a", quality=100, cycles_without_profit=NO_PROFIT_THRESHOLD - 1)
        loser = make_agent("b")
        run_competition([agent, loser], self.economy)
        # winner — only REWARD_WINNER applied, no extra pressure
        assert agent.credits == INITIAL + REWARD_WINNER

    def test_pressure_at_threshold(self):
        # loser at exactly the threshold → PENALTY_LOSER (loss) + PENALTY_LOSER*1 (pressure)
        winner = make_agent("w", quality=100)
        loser = make_agent("l", cycles_without_profit=NO_PROFIT_THRESHOLD)
        run_competition([winner, loser], self.economy)
        expected = INITIAL - PENALTY_LOSER - PENALTY_LOSER * 1
        assert loser.credits == pytest.approx(expected)

    def test_pressure_escalates_beyond_threshold(self):
        # loser at threshold + 2 → PENALTY_LOSER (loss) + PENALTY_LOSER*3 (pressure)
        winner = make_agent("w", quality=100)
        loser = make_agent("l", cycles_without_profit=NO_PROFIT_THRESHOLD + 2)
        run_competition([winner, loser], self.economy)
        pressure_multiplier = (NO_PROFIT_THRESHOLD + 2) - NO_PROFIT_THRESHOLD + 1  # == 3
        expected = INITIAL - PENALTY_LOSER - PENALTY_LOSER * pressure_multiplier
        assert loser.credits == pytest.approx(expected)

    def test_pressure_applies_to_winner_too(self):
        # even the winner gets temporal pressure if cycles_without_profit >= threshold
        winner = make_agent("w", quality=100, cycles_without_profit=NO_PROFIT_THRESHOLD)
        loser = make_agent("l")
        run_competition([winner, loser], self.economy)
        expected = INITIAL + REWARD_WINNER - PENALTY_LOSER * 1
        assert winner.credits == pytest.approx(expected)
