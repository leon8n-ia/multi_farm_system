import pytest
import pandas as pd

from config import INITIAL_CREDITS, REWARD_WINNER, PENALTY_LOSER
from farms.data_cleaning.farm import DataCleaningFarm
from farms.data_cleaning.producer_agent import ProducerAgent
from shared.models import Agent


# ---------------------------------------------------------------------------
# Fixture: CSV with 5 rows containing duplicates and nulls
# ---------------------------------------------------------------------------

CSV_CONTENT = """\
name,city,score
Alice,New York,90
ALICE,NEW YORK,90
Bob,,85
Carol,Boston,75
Carol,Boston,75
"""


@pytest.fixture
def dirty_csv(tmp_path):
    path = tmp_path / "dirty.csv"
    path.write_text(CSV_CONTENT)
    return str(path)


def make_producer(id: str) -> ProducerAgent:
    return ProducerAgent(Agent(id=id, credits=INITIAL_CREDITS))


# ---------------------------------------------------------------------------
# ProducerAgent.execute_task
# ---------------------------------------------------------------------------

class TestProducerAgentExecuteTask:
    def test_success(self, dirty_csv):
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.success is True

    def test_output_has_fewer_rows_than_input(self, dirty_csv):
        pa = make_producer("a")
        pa.execute_task(dirty_csv)
        assert pa.last_output is not None
        assert len(pa.last_output) < 5

    def test_output_rows_correct(self, dirty_csv):
        """5 rows → 2 rows after normalization + drop nulls + dedup."""
        pa = make_producer("a")
        pa.execute_task(dirty_csv)
        assert len(pa.last_output) == 2

    def test_strings_normalized_lowercase(self, dirty_csv):
        pa = make_producer("a")
        pa.execute_task(dirty_csv)
        df = pa.last_output
        str_cols = df.select_dtypes(include="str").columns
        for col in str_cols:
            assert df[col].str.lower().equals(df[col]), f"Column '{col}' not lowercase"

    def test_no_null_values(self, dirty_csv):
        pa = make_producer("a")
        pa.execute_task(dirty_csv)
        assert pa.last_output.isnull().sum().sum() == 0

    def test_no_duplicate_rows(self, dirty_csv):
        pa = make_producer("a")
        pa.execute_task(dirty_csv)
        df = pa.last_output
        assert len(df) == len(df.drop_duplicates())

    def test_quality_score_positive(self, dirty_csv):
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.quality_score > 0

    def test_speed_score_non_negative(self, dirty_csv):
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.speed_score >= 0

    def test_resource_efficiency_positive(self, dirty_csv):
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.resource_efficiency > 0

    def test_missing_file_returns_failure(self, tmp_path):
        pa = make_producer("a")
        result = pa.execute_task(str(tmp_path / "nonexistent.csv"))
        assert result.success is False

    def test_quality_score_formula(self, dirty_csv):
        """3 rows removed out of 5 → quality = 60.0."""
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.quality_score == pytest.approx(60.0)

    def test_resource_efficiency_formula(self, dirty_csv):
        """2 rows kept out of 5 → resource_efficiency = 40.0."""
        pa = make_producer("a")
        result = pa.execute_task(dirty_csv)
        assert result.resource_efficiency == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# DataCleaningFarm.run_production + run_competition
# ---------------------------------------------------------------------------

class TestDataCleaningFarm:
    def setup_method(self):
        pass

    def test_run_production_updates_agent_metrics(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        for pa in farm.producer_agents:
            assert pa.agent.quality > 0
            assert pa.agent.resource_efficiency > 0

    def test_run_competition_fills_output_buffer(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        farm.run_competition()
        assert len(farm.output_buffer) == 1

    def test_output_buffer_contains_dataframe(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        farm.run_competition()
        assert isinstance(farm.output_buffer[0], pd.DataFrame)

    def test_output_buffer_data_is_clean(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        farm.run_competition()
        result_df = farm.output_buffer[0]
        assert len(result_df) == 2
        assert result_df.isnull().sum().sum() == 0

    def test_run_cycle_increments_cycles_alive(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_cycle()
        assert farm.cycles_alive == 1

    def test_winner_receives_reward(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        farm.run_competition()
        credits = [pa.agent.credits for pa in farm.producer_agents]
        assert max(credits) == INITIAL_CREDITS + REWARD_WINNER

    def test_losers_receive_penalty(self, dirty_csv):
        farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                                input_path=dirty_csv)
        farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
        farm.run_production()
        farm.run_competition()
        credits = sorted([pa.agent.credits for pa in farm.producer_agents])
        assert credits[0] == INITIAL_CREDITS - PENALTY_LOSER
        assert credits[1] == INITIAL_CREDITS - PENALTY_LOSER
