"""DevOpsCloudFarm — produces DevOps cheat sheets via competing producer agents."""

import copy
import logging
import random

from datetime import datetime

from config import (
    COST_SELLER_LISTING,
    FARM_DEATH_THRESHOLD,
    INITIAL_CREDITS,
    REPRODUCTION_THRESHOLD,
)
from core.competition import run_competition as _run_competition
from core.economy import EconomyEngine
from farms.base_farm import BaseFarm
from farms.data_cleaning.revenue_bridge import LemonSqueezyRevenueBridge
from farms.devops_cloud.producer_agent_1 import DockerAgent
from farms.devops_cloud.producer_agent_2 import AWSAgent
from farms.devops_cloud.producer_agent_3 import K8sAgent
from farms.devops_cloud.seller_agent import DevOpsSellerAgent
from farms.gumroad_bridge import GumroadRevenueBridge
from farms.revenue_bridge_router import RevenueBridgeRouter
from shared.models import Agent, AgentStatus, FarmType

logger = logging.getLogger(__name__)

SALE_PROBABILITY = 0.35


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
        self.seller_agent = DevOpsSellerAgent(farm_id=id)
        self.product_type = "cheat_sheet"
        self.revenue_bridge = RevenueBridgeRouter([
            LemonSqueezyRevenueBridge(),
            GumroadRevenueBridge(),
        ], farm_type="devops_cloud")

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

        # Agent 2: AWS reference focus
        agent2 = Agent(
            id=f"{self.id}-aws-002",
            credits=float(INITIAL_CREDITS),
            strategy={
                "niche_focus": "devops_cloud",
                "product_type": "cheat_sheet",
                "product_variant": "aws_reference",
                "price_target": 24.0,
                "audience": "backend developers and cloud engineers",
                "output_format": "markdown",
                "quality_threshold": 0.88,
                "items_per_pack": 50,
            },
        )

        # Agent 3: Kubernetes prompts focus
        agent3 = Agent(
            id=f"{self.id}-k8s-003",
            credits=float(INITIAL_CREDITS),
            strategy={
                "niche_focus": "devops_cloud",
                "product_type": "cheat_sheet",
                "product_variant": "k8s_prompts",
                "price_target": 24.0,
                "audience": "DevOps engineers using Kubernetes",
                "output_format": "markdown",
                "quality_threshold": 0.88,
                "items_per_pack": 50,
            },
        )

        self.producer_agents = [
            DockerAgent(agent1),
            AWSAgent(agent2),
            K8sAgent(agent3),
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
                self.revenue_bridge.record_sale_attempt(price_usd=price, sold=True)
                self.revenue_bridge.publish_product(
                    title=title,
                    description=description,
                    price_usd=price,
                )
                # Upload to Backblaze storage
                file_name = f"cheatsheet_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
                self.revenue_bridge.upload_product_to_drive({"product": product, "listing": listing}, file_name)
                logger.info("[%s] SOLD: %s @ $%.2f", self.name, title, price)
            else:
                items_expired += 1
                self.seller_agent.sales_history.append({"sold": False, "price": 0.0})
                self.revenue_bridge.record_sale_attempt(price_usd=price, sold=False)

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

        # Create child agent of same type as parent
        if isinstance(parent_pa, AWSAgent):
            new_agent = AWSAgent(child)
        elif isinstance(parent_pa, K8sAgent):
            new_agent = K8sAgent(child)
        else:
            new_agent = DockerAgent(child)

        self.producer_agents.append(new_agent)
        logger.info("[%s] Agent %s reproduced -> %s (gen %d)", self.name, parent.id, child.id, child.generation)

    def calculate_performance(self) -> None:
        """Calculate farm ROI."""
        self.roi = self.profit / max(1.0, self.capital)
