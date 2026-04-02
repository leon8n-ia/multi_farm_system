import pytest
import pandas as pd
from unittest.mock import patch

from config import COST_SELLER_LISTING, INITIAL_CREDITS, REWARD_WINNER, PENALTY_LOSER
from farms.data_cleaning.farm import DataCleaningFarm, SALE_PROBABILITY
from farms.data_cleaning.producer_agent import ProducerAgent
from farms.data_cleaning.seller_agent import SellerAgent
from shared.models import Agent


# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture
def seller():
    return SellerAgent(farm_id="test-farm")


@pytest.fixture
def sample_df():
    return pd.DataFrame({"name": ["alice", "carol"], "city": ["new york", "boston"], "score": [90, 75]})


def make_producer(id: str) -> ProducerAgent:
    return ProducerAgent(Agent(id=id, credits=INITIAL_CREDITS))


def make_farm(dirty_csv) -> DataCleaningFarm:
    farm = DataCleaningFarm("f1", "Test Farm", capital=1000, credits=500,
                            input_path=dirty_csv)
    farm.producer_agents = [make_producer(f"a{i}") for i in range(3)]
    return farm


# ---------------------------------------------------------------------------
# SellerAgent — default strategy
# ---------------------------------------------------------------------------

class TestSellerAgentDefaults:
    def test_primary_channel(self, seller):
        assert seller.strategy["primary_channel"] == "gumroad"

    def test_pricing_model(self, seller):
        assert seller.strategy["pricing_model"] == "fixed"

    def test_base_price(self, seller):
        assert seller.strategy["base_price"] == 9.0

    def test_discount_threshold(self, seller):
        assert seller.strategy["discount_threshold"] == 3

    def test_discount_rate(self, seller):
        assert seller.strategy["discount_rate"] == pytest.approx(0.20)

    def test_listing_quality(self, seller):
        assert seller.strategy["listing_quality"] == "high"

    def test_target_audience(self, seller):
        assert seller.strategy["target_audience"] == "data scientists and ML engineers"

    def test_bundle_strategy(self, seller):
        assert seller.strategy["bundle_strategy"] is False

    def test_initial_revenue_zero(self, seller):
        assert seller.total_revenue == 0.0

    def test_initial_conversion_rate_zero(self, seller):
        assert seller.conversion_rate == 0.0


# ---------------------------------------------------------------------------
# prepare_listing
# ---------------------------------------------------------------------------

class TestPrepareListing:
    def test_returns_dict(self, seller, sample_df):
        listing = seller.prepare_listing(sample_df)
        assert isinstance(listing, dict)

    def test_contains_required_keys(self, seller, sample_df):
        listing = seller.prepare_listing(sample_df)
        assert {"channel", "price", "listing_quality", "target_audience",
                "bundle", "item_summary"} <= listing.keys()

    def test_channel_matches_strategy(self, seller, sample_df):
        listing = seller.prepare_listing(sample_df)
        assert listing["channel"] == "gumroad"

    def test_discount_applied_when_below_threshold(self, seller, sample_df):
        # 0 successful sales < threshold=3 → discount applied
        listing = seller.prepare_listing(sample_df)
        expected = round(9.0 * (1 - 0.20), 2)
        assert listing["price"] == pytest.approx(expected)

    def test_no_discount_when_threshold_reached(self, seller, sample_df):
        # Inject 3 successful sales into history
        seller.sales_history = [{"sold": True, "price": 9.0}] * 3
        listing = seller.prepare_listing(sample_df)
        assert listing["price"] == pytest.approx(9.0)

    def test_item_summary_includes_row_count(self, seller, sample_df):
        listing = seller.prepare_listing(sample_df)
        assert "2" in listing["item_summary"]  # 2 rows in sample_df


# ---------------------------------------------------------------------------
# calculate_seller_score
# ---------------------------------------------------------------------------

class TestCalculateSellerScore:
    def test_revenue_weight(self, seller):
        score = seller.calculate_seller_score({"revenue": 10})
        assert score == pytest.approx(100.0)

    def test_items_sold_weight(self, seller):
        score = seller.calculate_seller_score({"items_sold": 2})
        assert score == pytest.approx(10.0)

    def test_conversion_rate_weight(self, seller):
        score = seller.calculate_seller_score({"conversion_rate": 1.0})
        assert score == pytest.approx(20.0)

    def test_items_expired_penalty(self, seller):
        score = seller.calculate_seller_score({"items_expired": 2})
        assert score == pytest.approx(-6.0)

    def test_credits_spent_penalty(self, seller):
        score = seller.calculate_seller_score({"credits_spent": 10})
        assert score == pytest.approx(-5.0)

    def test_combined_formula(self, seller):
        results = {
            "revenue": 10,
            "items_sold": 2,
            "conversion_rate": 0.5,
            "items_expired": 1,
            "credits_spent": 4,
        }
        expected = 10 * 10 + 2 * 5 + 0.5 * 20 - 1 * 3 - 4 * 0.5
        assert seller.calculate_seller_score(results) == pytest.approx(expected)

    def test_empty_results_returns_zero(self, seller):
        assert seller.calculate_seller_score({}) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# update_strategy
# ---------------------------------------------------------------------------

class TestUpdateStrategy:
    def test_updates_existing_key(self, seller):
        seller.update_strategy({"base_price": 20.0})
        assert seller.strategy["base_price"] == 20.0

    def test_adds_new_key(self, seller):
        seller.update_strategy({"new_key": "value"})
        assert seller.strategy["new_key"] == "value"

    def test_does_not_remove_other_keys(self, seller):
        seller.update_strategy({"base_price": 20.0})
        assert "primary_channel" in seller.strategy


# ---------------------------------------------------------------------------
# report_to_farm
# ---------------------------------------------------------------------------

class TestReportToFarm:
    def test_contains_required_keys(self, seller):
        report = seller.report_to_farm()
        assert {"farm_id", "total_revenue", "conversion_rate",
                "avg_price", "total_sales", "credits", "strategy"} <= report.keys()

    def test_farm_id_matches(self, seller):
        assert seller.report_to_farm()["farm_id"] == "test-farm"

    def test_total_sales_counts_successes(self, seller):
        seller.sales_history = [
            {"sold": True, "price": 12.0},
            {"sold": False, "price": 0.0},
            {"sold": True, "price": 9.6},
        ]
        assert seller.report_to_farm()["total_sales"] == 2


# ---------------------------------------------------------------------------
# DataCleaningFarm.run_sales integration
# ---------------------------------------------------------------------------

class TestRunSales:
    def test_sold_updates_farm_profit(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()
        assert len(farm.output_buffer) == 1

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):  # 0.1 < 0.4 → sold
            farm.run_sales()

        assert farm.profit > 0

    def test_not_sold_profit_unchanged(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()

        with patch("farms.data_cleaning.farm.random.random", return_value=0.9):  # 0.9 > 0.4 → not sold
            farm.run_sales()

        assert farm.profit == 0.0

    def test_run_sales_clears_output_buffer(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):
            farm.run_sales()

        assert farm.output_buffer == []

    def test_sold_updates_total_revenue(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):
            farm.run_sales()

        assert farm.seller_agent.total_revenue > 0

    def test_listing_cost_deducted_from_seller(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()
        credits_before = farm.seller_agent.credits

        with patch("farms.data_cleaning.farm.random.random", return_value=0.9):
            farm.run_sales()

        assert farm.seller_agent.credits == credits_before - COST_SELLER_LISTING

    def test_sold_applies_discount_price(self, dirty_csv):
        """Fresh seller has 0 sales < threshold → discounted price used."""
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):
            farm.run_sales()

        discounted = round(9.0 * (1 - 0.20), 2)
        assert farm.seller_agent.total_revenue == pytest.approx(discounted)

    def test_conversion_rate_updated(self, dirty_csv):
        farm = make_farm(dirty_csv)
        farm.run_production()
        farm.run_competition()

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):
            farm.run_sales()

        assert farm.seller_agent.conversion_rate == pytest.approx(1.0)

    def test_run_cycle_includes_sales(self, dirty_csv):
        farm = make_farm(dirty_csv)

        with patch("farms.data_cleaning.farm.random.random", return_value=0.1):
            farm.run_cycle()

        assert len(farm.seller_agent.sales_history) == 1
