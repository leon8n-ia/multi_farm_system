import pytest

from config import (
    CAPITAL_BONUS_GOOD_FARM,
    CAPITAL_PENALTY_BAD_FARM,
    FARM_DEATH_THRESHOLD,
    FARM_EXPANSION_ROI,
    INITIAL_CREDITS,
)
from core.supervisor import GlobalSupervisor
from farms.data_cleaning.farm import DataCleaningFarm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def supervisor():
    return GlobalSupervisor()


@pytest.fixture
def csv_path(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("name\nalice\n")
    return str(p)


def make_farm(id, capital, roi=0.0, csv_path="dummy.csv"):
    farm = DataCleaningFarm(id, f"Farm {id}", capital=capital,
                            credits=float(INITIAL_CREDITS), input_path=csv_path)
    farm.roi = roi
    return farm


# ---------------------------------------------------------------------------
# redistribute_capital
# ---------------------------------------------------------------------------

class TestRedistributeCapital:
    def test_good_farm_receives_bonus(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.01, csv_path=csv_path)
        supervisor.redistribute_capital([farm])
        assert farm.capital == pytest.approx(1000 + CAPITAL_BONUS_GOOD_FARM)

    def test_bad_farm_loses_capital(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=-0.1, csv_path=csv_path)
        supervisor.redistribute_capital([farm])
        assert farm.capital == pytest.approx(1000 - CAPITAL_PENALTY_BAD_FARM)

    def test_neutral_farm_unchanged(self, supervisor, csv_path):
        # ROI >= 0 and <= FARM_EXPANSION_ROI → no change
        farm = make_farm("f1", capital=1000, roi=0.0, csv_path=csv_path)
        supervisor.redistribute_capital([farm])
        assert farm.capital == pytest.approx(1000)

    def test_roi_exactly_at_threshold_no_bonus(self, supervisor, csv_path):
        # roi == FARM_EXPANSION_ROI is NOT > threshold → no bonus
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI, csv_path=csv_path)
        supervisor.redistribute_capital([farm])
        assert farm.capital == pytest.approx(1000)

    def test_multiple_farms_each_evaluated_independently(self, supervisor, csv_path):
        good = make_farm("g", capital=1000, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        bad = make_farm("b", capital=1000, roi=-0.5, csv_path=csv_path)
        neutral = make_farm("n", capital=1000, roi=0.05, csv_path=csv_path)
        supervisor.redistribute_capital([good, bad, neutral])
        assert good.capital == pytest.approx(1000 + CAPITAL_BONUS_GOOD_FARM)
        assert bad.capital == pytest.approx(1000 - CAPITAL_PENALTY_BAD_FARM)
        assert neutral.capital == pytest.approx(1000)

    def test_returns_none(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, csv_path=csv_path)
        assert supervisor.redistribute_capital([farm]) is None


# ---------------------------------------------------------------------------
# eliminate_dead_farms
# ---------------------------------------------------------------------------

class TestEliminateDeadFarms:
    def test_farm_with_zero_capital_eliminated(self, supervisor, csv_path):
        farm = make_farm("f1", capital=float(FARM_DEATH_THRESHOLD), csv_path=csv_path)
        result = supervisor.eliminate_dead_farms([farm])
        assert result == []

    def test_farm_with_negative_capital_eliminated(self, supervisor, csv_path):
        farm = make_farm("f1", capital=-100.0, csv_path=csv_path)
        result = supervisor.eliminate_dead_farms([farm])
        assert result == []

    def test_farm_with_positive_capital_kept(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1.0, csv_path=csv_path)
        result = supervisor.eliminate_dead_farms([farm])
        assert len(result) == 1
        assert result[0] is farm

    def test_only_dead_farms_removed(self, supervisor, csv_path):
        alive1 = make_farm("a1", capital=500, csv_path=csv_path)
        dead = make_farm("d1", capital=0, csv_path=csv_path)
        alive2 = make_farm("a2", capital=1000, csv_path=csv_path)
        result = supervisor.eliminate_dead_farms([alive1, dead, alive2])
        assert len(result) == 2
        ids = [f.id for f in result]
        assert "a1" in ids and "a2" in ids and "d1" not in ids

    def test_empty_list_returns_empty(self, supervisor):
        assert supervisor.eliminate_dead_farms([]) == []

    def test_returns_new_list(self, supervisor, csv_path):
        farms = [make_farm("f1", capital=500, csv_path=csv_path)]
        result = supervisor.eliminate_dead_farms(farms)
        assert result is not farms  # new list object


# ---------------------------------------------------------------------------
# expand_if_warranted
# ---------------------------------------------------------------------------

class TestExpandIfWarranted:
    def test_adds_farm_when_best_roi_exceeds_threshold(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.01, csv_path=csv_path)
        farms = [farm]
        result = supervisor.expand_if_warranted(farms)
        assert len(result) == 2

    def test_no_expansion_when_roi_at_or_below_threshold(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI, csv_path=csv_path)
        farms = [farm]
        result = supervisor.expand_if_warranted(farms)
        assert len(result) == 1

    def test_no_expansion_when_roi_negative(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=-0.1, csv_path=csv_path)
        result = supervisor.expand_if_warranted([farm])
        assert len(result) == 1

    def test_clone_is_data_cleaning_farm(self, supervisor, csv_path):
        from farms.data_cleaning.farm import DataCleaningFarm
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        result = supervisor.expand_if_warranted([farm])
        clone = result[-1]
        assert isinstance(clone, DataCleaningFarm)

    def test_clone_has_different_id(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        result = supervisor.expand_if_warranted([farm])
        clone = result[-1]
        assert clone.id != farm.id

    def test_clone_has_same_capital_as_parent(self, supervisor, csv_path):
        farm = make_farm("f1", capital=2500, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        result = supervisor.expand_if_warranted([farm])
        clone = result[-1]
        assert clone.capital == pytest.approx(2500)

    def test_clone_has_producer_agents(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        result = supervisor.expand_if_warranted([farm])
        clone = result[-1]
        assert len(clone.producer_agents) >= 1

    def test_best_farm_chosen_for_expansion(self, supervisor, csv_path):
        poor = make_farm("poor", capital=1000, roi=0.05, csv_path=csv_path)
        rich = make_farm("rich", capital=999, roi=FARM_EXPANSION_ROI + 0.2, csv_path=csv_path)
        result = supervisor.expand_if_warranted([poor, rich])
        clone = result[-1]
        assert "rich" in clone.id

    def test_empty_farms_returns_empty(self, supervisor):
        assert supervisor.expand_if_warranted([]) == []

    def test_returns_same_list_object(self, supervisor, csv_path):
        farm = make_farm("f1", capital=1000, roi=FARM_EXPANSION_ROI + 0.1, csv_path=csv_path)
        farms = [farm]
        result = supervisor.expand_if_warranted(farms)
        assert result is farms
