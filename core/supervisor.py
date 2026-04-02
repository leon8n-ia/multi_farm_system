import logging
from typing import List

from config import (
    CAPITAL_BONUS_GOOD_FARM,
    CAPITAL_PENALTY_BAD_FARM,
    FARM_DEATH_THRESHOLD,
    FARM_EXPANSION_ROI,
)
from farms.base_farm import BaseFarm
from farms.farm_factory import FarmFactory

logger = logging.getLogger(__name__)


class GlobalSupervisor:
    """Oversees the entire farm portfolio: capital redistribution, culling, expansion."""

    def redistribute_capital(self, farms: List[BaseFarm]) -> None:
        """
        Reward high-ROI farms with CAPITAL_BONUS_GOOD_FARM.
        Penalise negative-ROI farms with CAPITAL_PENALTY_BAD_FARM.
        """
        for farm in farms:
            if farm.roi > FARM_EXPANSION_ROI:
                farm.capital += CAPITAL_BONUS_GOOD_FARM
                logger.info(
                    "[Supervisor] %s +$%d capital bonus (ROI=%.4f)",
                    farm.name, CAPITAL_BONUS_GOOD_FARM, farm.roi,
                )
            elif farm.roi < 0:
                farm.capital -= CAPITAL_PENALTY_BAD_FARM
                logger.info(
                    "[Supervisor] %s -$%d capital penalty (ROI=%.4f)",
                    farm.name, CAPITAL_PENALTY_BAD_FARM, farm.roi,
                )

    def eliminate_dead_farms(self, farms: List[BaseFarm]) -> List[BaseFarm]:
        """Remove farms whose capital has fallen to or below FARM_DEATH_THRESHOLD."""
        alive: List[BaseFarm] = []
        for farm in farms:
            if farm.capital <= FARM_DEATH_THRESHOLD:
                logger.info(
                    "[Supervisor] Farm %s eliminated (capital=%.2f)",
                    farm.name, farm.capital,
                )
            else:
                alive.append(farm)
        return alive

    def expand_if_warranted(self, farms: List[BaseFarm]) -> List[BaseFarm]:
        """
        If the best-performing farm has ROI > FARM_EXPANSION_ROI, spawn a clone
        via FarmFactory and append it to *farms*.
        Returns the (possibly extended) list.
        """
        if not farms:
            return farms
        best = max(farms, key=lambda f: f.roi)
        if best.roi > FARM_EXPANSION_ROI:
            new_farm = FarmFactory.create_similar(best)
            farms.append(new_farm)
            logger.info(
                "[Supervisor] Expansion triggered: %s cloned from %s (ROI=%.4f)",
                new_farm.id, best.id, best.roi,
            )
        return farms
