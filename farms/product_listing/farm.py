import copy
import logging
import random
from datetime import datetime

from config import COST_SELLER_LISTING, FARM_DEATH_THRESHOLD, GUMROAD_PRODUCT_IDS, INITIAL_CREDITS, REPRODUCTION_THRESHOLD
from core.competition import run_competition as _run_competition
from core.economy import EconomyEngine
from farms.base_farm import BaseFarm
from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge
from farms.gumroad_bridge import GumroadRevenueBridge
from farms.product_listing.producer_agent import ProducerAgent
from farms.revenue_bridge_router import RevenueBridgeRouter
from farms.seller_agent import SellerAgent
from shared.models import Agent, AgentStatus, FarmType

logger = logging.getLogger(__name__)

SALE_PROBABILITY = 0.40

_DEFAULT_PRODUCTS = ["digital-product", "resume-template", "social-media-kit"]
_NICHES = ["mercadolibre_latam", "electronics", "home_garden"]

_DEFAULT_STRATEGY: dict = {
    "primary_channel": "etsy",
    "pricing_model": "fixed",
    "base_price": 4.0,
    "discount_threshold": 5,
    "discount_rate": 0.10,
    "listing_quality": "high",
    "target_audience": "ecommerce sellers latam",
    "bundle_strategy": True,
    "niche_focus": "mercadolibre_latam",
    "output_format": "json",
}


class ProductListingFarm(BaseFarm):
    def __init__(
        self,
        id: str,
        name: str,
        capital: float,
        credits: float,
        product_names: list[str] | None = None,
    ) -> None:
        super().__init__(id, name, FarmType.MIXED, capital, credits)
        self.product_names: list[str] = product_names or list(_DEFAULT_PRODUCTS)
        self.niches = list(_NICHES)
        self.economy = EconomyEngine()
        self.seller_agent = SellerAgent(farm_id=id, strategy=dict(_DEFAULT_STRATEGY))
        self.revenue_bridge = RevenueBridgeRouter([
            LemonSqueezyRevenueBridge(),
            GumroadRevenueBridge(product_id=GUMROAD_PRODUCT_IDS["product_listing"]),
        ], farm_type="product_listing")
        self.product_type = "product_listing"

    def _current_product(self) -> str:
        return self.product_names[self.cycles_alive % len(self.product_names)]

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
        product = self._current_product()
        for pa in self.producer_agents:
            result = pa.execute_task(product)
            if result.success:
                pa.agent.quality = result.quality_score
                pa.agent.speed = result.speed_score
                pa.agent.resource_efficiency = result.resource_efficiency

    def run_competition(self) -> Agent:
        agents = [pa.agent for pa in self.producer_agents]
        winner = _run_competition(agents, self.economy)
        winning_pa = next(pa for pa in self.producer_agents if pa.agent is winner)
        if winning_pa.last_output is not None:
            self.output_buffer.append(winning_pa.last_output)
        return winner

    def run_sales(self) -> None:
        if not self.output_buffer:
            logger.info("[%s] No items to sell this cycle.", self.name)
            return

        niche = self._current_niche()
        self.seller_agent.strategy["niche_focus"] = niche
        niche_label = niche.replace("_", " ").title()
        output_fmt = self.seller_agent.strategy.get("output_format", "json")
        audience = self.seller_agent.strategy["target_audience"]
        items_sold = items_expired = 0
        revenue = credits_spent = 0.0

        for item in self.output_buffer:
            listing = self.seller_agent.prepare_listing(item)
            listing["title"] = f"{niche_label} Product Listing [{output_fmt.upper()}]"
            listing["description"] = (
                f"Ready-to-publish {niche_label.lower()} product listing — "
                f"optimized title, description, tags, and pricing. "
                f"Format: {output_fmt.upper()}. For {audience}."
            )
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
                    title=listing.get("title", "Product Listing"),
                    description=listing.get("description", ""),
                    price_usd=price,
                )
                # Upload to Google Drive
                file_name = f"listing_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                self.revenue_bridge.upload_product_to_drive(item, file_name)
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
                sold_prices = [s["price"] for s in self.seller_agent.sales_history if s["sold"]]
                self.seller_agent.avg_price = sum(sold_prices) / len(sold_prices)

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
                logger.info("[%s] Agent %s died (credits=%.2f)", self.name, pa.agent.id, pa.agent.credits)
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
            credits=float(INITIAL_CREDITS),
            generation=parent.generation + 1,
            parent_id=parent.id,
            strategy=copy.deepcopy(parent.strategy),
        )
        self.producer_agents.append(ProducerAgent(child))
        logger.info("[%s] Agent %s reproduced -> %s (gen %d)", self.name, parent.id, child.id, child.generation)

    def calculate_performance(self) -> None:
        self.roi = self.profit / max(1.0, self.capital)
