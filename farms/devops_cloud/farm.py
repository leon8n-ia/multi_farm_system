"""DevOpsCloudFarm — produces DevOps cheat sheets via competing producer agents."""

import copy
import logging
import random

from config import (
    COST_SELLER_LISTING,
    FARM_DEATH_THRESHOLD,
    INITIAL_CREDITS,
    REPRODUCTION_THRESHOLD,
)
from core.competition import run_competition as _run_competition
from core.economy import EconomyEngine
from farms.base_farm import BaseFarm
from farms.devops_cloud.producer_agent_1 import DockerAgent
from farms.seller_agent import SellerAgent
from shared.models import Agent, AgentStatus, FarmType

logger = logging.getLogger(__name__)

SALE_PROBABILITY = 0.35

_DEFAULT_SELLER_STRATEGY: dict = {
    "primary_channel": "gumroad",
    "pricing_model": "tiered",
    "base_price": 24.0,
    "discount_threshold": 3,
    "discount_rate": 0.15,
    "listing_quality": "high",
    "target_audience": "DevOps engineers and backend developers",
    "bundle_strategy": True,
    "niche_focus": "devops_cloud",
    "output_format": "markdown",
}


class DevOpsCloudFarm(BaseFarm):
    """Farm that produces DevOps cheat sheets via competing producer agents."""

    def __init__(
        self,
        id: str,
        name: str = "DevOps Cloud Farm",
        capital: float = 1000.0,
        credits: float = 500.0,
    ) -> None:
        super().__init__(id, name, FarmType.DEVOPS_CLOUD, capital, credits)
        self.economy = EconomyEngine()
        self.seller_agent = SellerAgent(farm_id=id, strategy=dict(_DEFAULT_SELLER_STRATEGY))
        self.product_type = "cheat_sheet"

        # Initialize 3 competing producer agents
        self._init_producer_agents()

    def _init_producer_agents(self) -> None:
        """Initialize the 3 competing producer agents with varied strategies."""
        # Agent 1: Docker workflow focus
        agent1 = Agent(
            id=f"{self.id}-docker-001",
            credits=float(INITIAL_CREDITS),
            strategy={
                "niche_focus": "devops_cloud",
                "product_type": "cheat_sheet",
                "product_variant": "docker_workflow",
                "price_target": 24.0,
                "audience": "DevOps engineers and backend developers",
                "output_format": "markdown",
                "quality_threshold": 0.88,
                "items_per_pack": 50,
            },
        )

        # Agent 2: Kubernetes focus
        agent2 = Agent(
            id=f"{self.id}-k8s-002",
            credits=float(INITIAL_CREDITS),
            strategy={
                "niche_focus": "devops_cloud",
                "product_type": "cheat_sheet",
                "product_variant": "kubernetes_essentials",
                "price_target": 29.0,
                "audience": "Platform engineers and SREs",
                "output_format": "markdown",
                "quality_threshold": 0.90,
                "items_per_pack": 60,
            },
        )

        # Agent 3: CI/CD pipelines focus
        agent3 = Agent(
            id=f"{self.id}-cicd-003",
            credits=float(INITIAL_CREDITS),
            strategy={
                "niche_focus": "devops_cloud",
                "product_type": "cheat_sheet",
                "product_variant": "cicd_pipelines",
                "price_target": 19.0,
                "audience": "Software engineers automating deployments",
                "output_format": "markdown",
                "quality_threshold": 0.85,
                "items_per_pack": 40,
            },
        )

        self.producer_agents = [
            DockerAgent(agent1),
            DockerAgent(agent2),
            DockerAgent(agent3),
        ]

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
        """Each agent produces a product using their strategy."""
        for pa in self.producer_agents:
            variant = pa.agent.strategy.get("product_variant", "docker_workflow")
            result = pa.execute_task(variant)
            if result.success:
                pa.agent.quality = result.quality_score
                pa.agent.speed = result.speed_score
                pa.agent.resource_efficiency = result.resource_efficiency
                logger.info(
                    "[%s] %s produced: %s (quality=%.1f)",
                    self.name, pa.agent.id, result.description, result.quality_score
                )

    def run_competition(self) -> Agent:
        """Run competition among agents to select the best product."""
        agents = [pa.agent for pa in self.producer_agents]
        winner = _run_competition(agents, self.economy)
        winning_pa = next(pa for pa in self.producer_agents if pa.agent is winner)
        if winning_pa.last_output is not None:
            self.output_buffer.append(winning_pa.last_output)
        logger.info("[%s] Competition winner: %s", self.name, winner.id)
        return winner

    def run_sales(self) -> None:
        """Attempt to sell products in the output buffer."""
        if not self.output_buffer:
            logger.info("[%s] No items to sell this cycle.", self.name)
            return

        items_sold = items_expired = 0
        revenue = credits_spent = 0.0

        for product in self.output_buffer:
            title = product.get("title", "DevOps Cheat Sheet")
            description = product.get("description", "Essential commands for DevOps engineers.")
            price = product.get("price", self.seller_agent.strategy.get("base_price", 24.0))

            listing = self.seller_agent.prepare_listing(product)
            listing["title"] = title
            listing["description"] = description
            listing["price"] = price

            self.seller_agent.credits -= COST_SELLER_LISTING
            credits_spent += COST_SELLER_LISTING

            if random.random() < SALE_PROBABILITY:
                items_sold += 1
                revenue += price
                self.seller_agent.total_revenue += price
                self.seller_agent.sales_history.append({"sold": True, "price": price})
                logger.info("[%s] SOLD: %s @ $%.2f", self.name, title, price)
            else:
                items_expired += 1
                self.seller_agent.sales_history.append({"sold": False, "price": 0.0})

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
        """Apply economic costs to all agents."""
        for pa in self.producer_agents:
            self.economy.apply_cost_of_living(pa.agent)
            self.economy.apply_action_cost(pa.agent)

    def eliminate_dead(self) -> None:
        """Remove agents that have run out of credits."""
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
        """Create offspring from successful agents."""
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

        self.producer_agents.append(DockerAgent(child))
        logger.info("[%s] Agent %s reproduced -> %s (gen %d)", self.name, parent.id, child.id, child.generation)

    def calculate_performance(self) -> None:
        """Calculate farm ROI."""
        self.roi = self.profit / max(1.0, self.capital)
