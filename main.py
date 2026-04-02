import logging
import time

from rich.console import Console

from config import CYCLE_INTERVAL_SECONDS, INITIAL_CREDITS
from core.supervisor import GlobalSupervisor
from farms.auto_reports.farm import AutoReportsFarm
from farms.auto_reports.producer_agent import ProducerAgent as ARProducer
from farms.base_farm import BaseFarm
from farms.data_cleaning.farm import DataCleaningFarm
from farms.data_cleaning.producer_agent import ProducerAgent as DCProducer
from farms.monetized_content.farm import MonetizedContentFarm
from farms.monetized_content.producer_agent import ProducerAgent as MCProducer
from farms.product_listing.farm import ProductListingFarm
from farms.product_listing.producer_agent import ProducerAgent as PLProducer
from farms.traffic.farm import TrafficFarm
from observatory.dashboard import Dashboard
from observatory.logger import log_economic_event
from observatory.memory import Memory
from shared.models import Agent, SaleResult

# Direct farm/module logs to a file so the Rich dashboard owns the terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    filename="observatory/app.log",
    encoding="utf-8",
)

console = Console(legacy_windows=False)
CSV_PATH = "data/sample.csv"
N_PRODUCERS = 3
SUPERVISOR_INTERVAL = 10  # run supervisor every N cycles


# ---------------------------------------------------------------------------
# Farm builders
# ---------------------------------------------------------------------------

def _build_dc_farm() -> DataCleaningFarm:
    farm = DataCleaningFarm(
        id="dc-farm-1",
        name="Data Cleaning #1",
        capital=1000.0,
        credits=500.0,
        input_path=CSV_PATH,
    )
    for i in range(N_PRODUCERS):
        farm.producer_agents.append(
            DCProducer(Agent(id=f"dc-producer-{i}", credits=float(INITIAL_CREDITS)))
        )
    return farm


def _build_ar_farm() -> AutoReportsFarm:
    farm = AutoReportsFarm(
        id="ar-farm-1",
        name="Auto Reports #1",
        capital=1000.0,
        credits=500.0,
        topic="quarterly",
    )
    for i in range(N_PRODUCERS):
        farm.producer_agents.append(
            ARProducer(Agent(id=f"ar-producer-{i}", credits=float(INITIAL_CREDITS)))
        )
    return farm


def _build_pl_farm() -> ProductListingFarm:
    farm = ProductListingFarm(
        id="pl-farm-1",
        name="Product Listing #1",
        capital=800.0,
        credits=500.0,
    )
    for i in range(N_PRODUCERS):
        farm.producer_agents.append(
            PLProducer(Agent(id=f"pl-producer-{i}", credits=float(INITIAL_CREDITS)))
        )
    return farm


def _build_mc_farm() -> MonetizedContentFarm:
    farm = MonetizedContentFarm(
        id="mc-farm-1",
        name="Monetized Content #1",
        capital=900.0,
        credits=500.0,
    )
    for i in range(N_PRODUCERS):
        farm.producer_agents.append(
            MCProducer(Agent(id=f"mc-producer-{i}", credits=float(INITIAL_CREDITS)))
        )
    return farm


def _build_traffic_farm() -> TrafficFarm:
    return TrafficFarm(
        id="traffic-farm-1",
        name="Traffic #1 (Reddit)",
        capital=500.0,
        credits=500.0,
        store_url="https://multifarm.lemonsqueezy.com",
    )


def build_farms() -> list[BaseFarm]:
    return [
        _build_dc_farm(),
        _build_ar_farm(),
        _build_pl_farm(),
        _build_mc_farm(),
        _build_traffic_farm(),
    ]


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def _persist_cycle(memory: Memory, farm: BaseFarm, cycle: int) -> None:
    memory.save_cycle(farm, cycle)
    for pa in farm.producer_agents:
        memory.save_agent(pa.agent, farm_id=farm.id)
    history = farm.seller_agent.sales_history
    if history:
        last = history[-1]
        item_label = getattr(farm, "product_type", "product")
        sale = SaleResult(sold=last["sold"], usd_amount=last["price"], item=item_label)
        memory.save_sale(sale, farm_id=farm.id)
        log_economic_event(
            event_type="sale",
            agent_id=farm.seller_agent.farm_id,
            amount=last["price"],
            balance=farm.seller_agent.total_revenue,
            sold=last["sold"],
            cycle=cycle,
        )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    memory = Memory()
    dashboard = Dashboard(console=console)
    supervisor = GlobalSupervisor()
    farms: list[BaseFarm] = build_farms()
    cycle = 1

    console.rule("[bold cyan]Multi-Farm System Starting[/bold cyan]", style="cyan")

    while True:
        console.print(f"\n[bold]>> CICLO {cycle}[/bold]", highlight=False)

        for farm in list(farms):  # snapshot: supervisor may append new farms mid-loop
            prev_len = len(farm.seller_agent.sales_history)
            farm.run_cycle()
            for sale_record in farm.seller_agent.sales_history[prev_len:]:
                dashboard.log_sale(sale_record, farm_name=farm.name)
            _persist_cycle(memory, farm, cycle)

        # Global supervisor runs every SUPERVISOR_INTERVAL cycles
        if cycle % SUPERVISOR_INTERVAL == 0:
            console.print("[dim]-- Supervisor running --[/dim]", highlight=False)
            supervisor.redistribute_capital(farms)
            farms = supervisor.eliminate_dead_farms(farms)
            farms = supervisor.expand_if_warranted(farms)
            log_economic_event(
                event_type="supervisor_cycle",
                agent_id="supervisor",
                amount=0.0,
                balance=sum(f.capital for f in farms),
                farms=len(farms),
                cycle=cycle,
            )

        dashboard.update(farms, cycle)
        cycle += 1
        time.sleep(CYCLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
