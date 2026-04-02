import copy
import logging
import random

from core.competition import run_competition as _run_competition
from core.economy import EconomyEngine
from config import COST_SELLER_LISTING, FARM_DEATH_THRESHOLD, GUMROAD_PRODUCT_IDS, INITIAL_CREDITS, REPRODUCTION_THRESHOLD
from farms.base_farm import BaseFarm
from farms.data_cleaning.producer_agent import ProducerAgent
from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge
from farms.data_cleaning.seller_agent import SellerAgent
from farms.gumroad_bridge import GumroadRevenueBridge
from farms.revenue_bridge_router import RevenueBridgeRouter
from shared.models import Agent, AgentStatus, FarmType

logger = logging.getLogger(__name__)

SALE_PROBABILITY = 0.40
_NICHES = ["ecommerce", "fintech", "saas_metrics"]


class DataCleaningFarm(BaseFarm):
    def __init__(
        self,
        id: str,
        name: str,
        capital: float,
        credits: float,
        input_path: str,
    ) -> None:
        super().__init__(id, name, FarmType.CROP, capital, credits)
        self.input_path = input_path
        self.niches = list(_NICHES)
        self.economy = EconomyEngine()
        self.seller_agent = SellerAgent(farm_id=id)
        self.revenue_bridge = RevenueBridgeRouter([
            LemonSqueezyRevenueBridge(),
            GumroadRevenueBridge(product_id=GUMROAD_PRODUCT_IDS["data_cleaning"]),
        ])
        self.product_type = "cleaned_dataset"

    def _current_niche(self) -> str:
        return self.niches[self.cycles_alive % len(self.niches)]

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run_cycle(self) -> None:
        self.run_production()
        self.run_competition()
        self.run_sales()
        self.apply_economics()
        self.eliminate_dead()
        self.reproduce_winners()
        self.calculate_performance()
        self.cycles_alive += 1

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def run_production(self) -> None:
        """Give every producer agent the same cleaning task and collect results."""
        for pa in self.producer_agents:
            result = pa.execute_task(self.input_path)
            if result.success:
                pa.agent.quality = result.quality_score
                pa.agent.speed = result.speed_score
                pa.agent.resource_efficiency = result.resource_efficiency

    def run_competition(self) -> Agent:
        """Score all agents, apply rewards/penalties, store winner's output."""
        agents = [pa.agent for pa in self.producer_agents]
        winner = _run_competition(agents, self.economy)
        winning_pa = next(pa for pa in self.producer_agents if pa.agent is winner)
        if winning_pa.last_output is not None:
            self.output_buffer.append(winning_pa.last_output)
        return winner

    def run_sales(self) -> None:
        """Attempt to sell every item in output_buffer, then clear it."""
        if not self.output_buffer:
            logger.info("[%s] No items to sell this cycle.", self.name)
            return

        self.seller_agent.strategy["niche_focus"] = self._current_niche()
        items_sold = 0
        items_expired = 0
        revenue = 0.0
        credits_spent = 0.0

        for item in self.output_buffer:
            listing = self.seller_agent.prepare_listing(item)
            self.seller_agent.credits -= COST_SELLER_LISTING
            credits_spent += COST_SELLER_LISTING

            if random.random() < SALE_PROBABILITY:
                price = listing["price"]
                items_sold += 1
                revenue += price
                self.seller_agent.total_revenue += price
                self.seller_agent.sales_history.append({"sold": True, "price": price})
                self.revenue_bridge.record_sale_attempt(price_usd=price, sold=True)
                self.revenue_bridge.publish_product(
                    title=listing.get("title", "Cleaned Dataset"),
                    description=listing.get("description", ""),
                    price_usd=price,
                )
            else:
                items_expired += 1
                self.seller_agent.sales_history.append({"sold": False, "price": 0.0})
                self.revenue_bridge.record_sale_attempt(
                    price_usd=listing["price"], sold=False
                )

        self.output_buffer.clear()

        total_attempts = items_sold + items_expired
        if total_attempts > 0:
            self.seller_agent.conversion_rate = items_sold / total_attempts
            if items_sold > 0:
                sold_prices = [
                    s["price"] for s in self.seller_agent.sales_history if s["sold"]
                ]
                self.seller_agent.avg_price = (
                    sum(sold_prices) / len(sold_prices) if sold_prices else 0.0
                )

        self.profit += revenue

        cycle_results = {
            "revenue": revenue,
            "items_sold": items_sold,
            "conversion_rate": self.seller_agent.conversion_rate,
            "items_expired": items_expired,
            "credits_spent": credits_spent,
        }
        score = self.seller_agent.calculate_seller_score(cycle_results)
        logger.info(
            "[%s] Sales: %d/%d sold | revenue=$%.2f | seller_score=%.1f",
            self.name, items_sold, total_attempts, revenue, score,
        )

    def apply_economics(self) -> None:
        for pa in self.producer_agents:
            self.economy.apply_cost_of_living(pa.agent)
            self.economy.apply_action_cost(pa.agent)

    def eliminate_dead(self) -> None:
        alive = []
        for pa in self.producer_agents:
            if pa.agent.credits <= FARM_DEATH_THRESHOLD:
                pa.agent.status = AgentStatus.DEAD
                self.dead_agents.append(pa)
                logger.info(
                    "[%s] Agent %s died (credits=%.2f)",
                    self.name, pa.agent.id, pa.agent.credits,
                )
            else:
                alive.append(pa)
        self.producer_agents = alive

    def reproduce_winners(self) -> None:
        if not self.producer_agents or self.profit < REPRODUCTION_THRESHOLD:
            return
        parent_pa = max(self.producer_agents, key=lambda pa: pa.agent.credits)
        parent = parent_pa.agent
        child = Agent(
            id=f"{parent.id}-gen{parent.generation + 1}",
            credits=INITIAL_CREDITS,
            generation=parent.generation + 1,
            parent_id=parent.id,
            strategy=copy.deepcopy(parent.strategy),
        )
        self.producer_agents.append(ProducerAgent(child))
        logger.info(
            "[%s] Agent %s reproduced → %s (gen %d)",
            self.name, parent.id, child.id, child.generation,
        )

    def calculate_performance(self) -> None:
        self.roi = self.profit / max(1.0, self.capital)

    def build_farm_context(self) -> dict:
        """Return a context dict for mutate_strategy, including market feedback."""
        return {
            "farm_id": self.id,
            "farm_name": self.name,
            "capital": self.capital,
            "profit": self.profit,
            "roi": self.roi,
            "market_feedback": self.revenue_bridge.get_market_feedback(),
        }
