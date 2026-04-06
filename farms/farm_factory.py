import logging

from config import DEVOPS_CLOUD_FARM_ACTIVE, MOBILE_DEV_FARM_ACTIVE, INITIAL_CREDITS
from farms.base_farm import BaseFarm

logger = logging.getLogger(__name__)

_DEFAULT_PRODUCERS = 2


class FarmFactory:
    _counter: int = 0

    @classmethod
    def create_similar(cls, farm: BaseFarm) -> BaseFarm:
        """Clone *farm* into a fresh farm of the same type with a new id."""
        # Inline imports avoid circular dependencies at module load time
        from farms.auto_reports.farm import AutoReportsFarm
        from farms.data_cleaning.farm import DataCleaningFarm
        from farms.devops_cloud.farm import DevOpsCloudFarm
        from farms.mobile_dev.farm import MobileDevFarm
        from farms.monetized_content.farm import MonetizedContentFarm
        from farms.product_listing.farm import ProductListingFarm
        from farms.traffic.farm import TrafficFarm
        from shared.models import Agent

        cls._counter += 1
        new_id = f"{farm.id}-exp{cls._counter}"
        new_name = f"{farm.name} (Expansion {cls._counter})"

        # TrafficFarm has no producer agents — return early
        if isinstance(farm, TrafficFarm):
            new_farm = TrafficFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
                store_url=farm.store_url,
            )
            logger.info(
                "[FarmFactory] Created %s from %s (TrafficFarm — no producers)",
                new_id, farm.id,
            )
            return new_farm

        if isinstance(farm, DataCleaningFarm):
            from farms.data_cleaning.producer_agent import ProducerAgent
            new_farm = DataCleaningFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
                input_path=farm.input_path,
            )
            ProducerCls = ProducerAgent

        elif isinstance(farm, AutoReportsFarm):
            from farms.auto_reports.producer_agent import ProducerAgent
            new_farm = AutoReportsFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
                topic=farm.topic,
            )
            ProducerCls = ProducerAgent

        elif isinstance(farm, ProductListingFarm):
            from farms.product_listing.producer_agent import ProducerAgent
            new_farm = ProductListingFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
                product_names=list(farm.product_names),
            )
            ProducerCls = ProducerAgent

        elif isinstance(farm, MonetizedContentFarm):
            from farms.monetized_content.producer_agent import ProducerAgent
            new_farm = MonetizedContentFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
                niches=list(farm.niches),
            )
            ProducerCls = ProducerAgent

        elif DEVOPS_CLOUD_FARM_ACTIVE and isinstance(farm, DevOpsCloudFarm):
            from farms.devops_cloud.producer_agent_1 import DockerAgent
            new_farm = DevOpsCloudFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
            )
            # DevOpsCloudFarm initializes its own agents, return early
            logger.info(
                "[FarmFactory] Created %s from %s (DevOpsCloudFarm — 3 producers)",
                new_id, farm.id,
            )
            return new_farm

        elif MOBILE_DEV_FARM_ACTIVE and isinstance(farm, MobileDevFarm):
            from farms.mobile_dev.producer_agent_1 import ReactNativeAgent
            new_farm = MobileDevFarm(
                id=new_id, name=new_name,
                capital=farm.capital, credits=float(INITIAL_CREDITS),
            )
            # MobileDevFarm initializes its own agents, return early
            logger.info(
                "[FarmFactory] Created %s from %s (MobileDevFarm)",
                new_id, farm.id,
            )
            return new_farm

        else:
            raise NotImplementedError(f"FarmFactory does not support {type(farm).__name__}")

        n_producers = max(_DEFAULT_PRODUCERS, len(farm.producer_agents))
        for i in range(n_producers):
            new_farm.producer_agents.append(
                ProducerCls(Agent(id=f"{new_id}-producer-{i}", credits=float(INITIAL_CREDITS)))
            )

        logger.info(
            "[FarmFactory] Created %s from %s (%d producers)",
            new_id, farm.id, n_producers,
        )
        return new_farm
