import pytest

from config import FARM_DEATH_THRESHOLD, INITIAL_CREDITS, REPRODUCTION_THRESHOLD
from farms.data_cleaning.farm import DataCleaningFarm
from farms.data_cleaning.producer_agent import ProducerAgent
from shared.models import Agent, AgentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_farm(tmp_path) -> DataCleaningFarm:
    csv = tmp_path / "x.csv"
    csv.write_text("name\nalice\n")
    return DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                            input_path=str(csv))


def make_pa(id: str, credits: float, generation: int = 0,
            strategy: dict | None = None) -> ProducerAgent:
    agent = Agent(id=id, credits=credits, generation=generation,
                  strategy=strategy or {})
    return ProducerAgent(agent)


# ---------------------------------------------------------------------------
# eliminate_dead
# ---------------------------------------------------------------------------

class TestEliminateDead:
    def test_agent_with_zero_credits_eliminated(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("dead", credits=0.0)]
        farm.eliminate_dead()
        assert len(farm.producer_agents) == 0

    def test_agent_with_negative_credits_eliminated(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("dead", credits=-10.0)]
        farm.eliminate_dead()
        assert len(farm.producer_agents) == 0

    def test_alive_agent_not_eliminated(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("alive", credits=1.0)]
        farm.eliminate_dead()
        assert len(farm.producer_agents) == 1

    def test_only_dead_removed_mixed_population(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [
            make_pa("alive1", credits=50.0),
            make_pa("dead1", credits=0.0),
            make_pa("alive2", credits=100.0),
            make_pa("dead2", credits=-5.0),
        ]
        farm.eliminate_dead()
        ids = [pa.agent.id for pa in farm.producer_agents]
        assert ids == ["alive1", "alive2"]

    def test_dead_agents_saved_to_dead_agents_list(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("dead", credits=0.0)]
        farm.eliminate_dead()
        assert len(farm.dead_agents) == 1
        assert farm.dead_agents[0].agent.id == "dead"

    def test_dead_agent_status_set_to_dead(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("dead", credits=0.0)]
        farm.eliminate_dead()
        assert farm.dead_agents[0].agent.status == AgentStatus.DEAD

    def test_alive_agent_not_added_to_dead_agents(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("alive", credits=50.0)]
        farm.eliminate_dead()
        assert farm.dead_agents == []

    def test_dead_agents_accumulate_across_calls(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("dead1", credits=0.0)]
        farm.eliminate_dead()
        farm.producer_agents = [make_pa("dead2", credits=0.0)]
        farm.eliminate_dead()
        assert len(farm.dead_agents) == 2


# ---------------------------------------------------------------------------
# reproduce_winners
# ---------------------------------------------------------------------------

class TestReproduceWinners:
    def test_no_reproduction_below_threshold(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS)]
        farm.profit = REPRODUCTION_THRESHOLD - 1
        farm.reproduce_winners()
        assert len(farm.producer_agents) == 1

    def test_no_reproduction_at_zero_profit(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS)]
        farm.profit = 0.0
        farm.reproduce_winners()
        assert len(farm.producer_agents) == 1

    def test_reproduction_at_threshold(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        assert len(farm.producer_agents) == 2

    def test_clone_has_initial_credits(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=999.0)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.credits == INITIAL_CREDITS

    def test_clone_generation_is_one(self, tmp_path):
        """Parent gen=0 → clone gen=1."""
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS, generation=0)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.generation == 1

    def test_clone_generation_increments(self, tmp_path):
        """Parent gen=2 → clone gen=3."""
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS, generation=2)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.generation == 3

    def test_clone_parent_id_correct(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("producer-0", credits=INITIAL_CREDITS)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.parent_id == "producer-0"

    def test_clone_id_format(self, tmp_path):
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("producer-0", credits=INITIAL_CREDITS, generation=0)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.id == "producer-0-gen1"

    def test_winner_selected_by_most_credits(self, tmp_path):
        """Among multiple agents, the richest one reproduces."""
        farm = make_farm(tmp_path)
        farm.producer_agents = [
            make_pa("poor", credits=50.0),
            make_pa("rich", credits=999.0),
            make_pa("mid", credits=300.0),
        ]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.parent_id == "rich"

    def test_clone_strategy_is_copy_of_parent(self, tmp_path):
        farm = make_farm(tmp_path)
        parent_strategy = {"pricing_model": "dynamic", "base_price": 15.0}
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS,
                                        strategy=parent_strategy)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        clone = farm.producer_agents[-1]
        assert clone.agent.strategy == parent_strategy

    def test_clone_strategy_is_independent_reference(self, tmp_path):
        """Mutating parent strategy must not affect clone."""
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa("a", credits=INITIAL_CREDITS,
                                        strategy={"base_price": 12.0})]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        parent_pa = farm.producer_agents[0]
        clone = farm.producer_agents[-1]
        parent_pa.agent.strategy["base_price"] = 99.0
        assert clone.agent.strategy["base_price"] == 12.0

    def test_only_one_clone_per_call(self, tmp_path):
        """Even with many rich agents, reproduce_winners creates exactly one clone."""
        farm = make_farm(tmp_path)
        farm.producer_agents = [make_pa(f"a{i}", credits=999.0) for i in range(5)]
        farm.profit = REPRODUCTION_THRESHOLD
        farm.reproduce_winners()
        assert len(farm.producer_agents) == 6
