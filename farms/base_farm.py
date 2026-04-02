from abc import ABC, abstractmethod
from typing import Any, List

from shared.models import FarmType


class BaseFarm(ABC):
    def __init__(
        self,
        id: str,
        name: str,
        farm_type: FarmType,
        capital: float,
        credits: float,
    ) -> None:
        self.id = id
        self.name = name
        self.farm_type = farm_type
        self.capital = capital
        self.credits = credits
        self.producer_agents: List[Any] = []
        self.output_buffer: List[Any] = []
        self.dead_agents: List[Any] = []
        self.profit: float = 0.0
        self.roi: float = 0.0
        self.cycles_alive: int = 0

    @abstractmethod
    def run_cycle(self) -> None: ...

    @abstractmethod
    def run_production(self) -> None: ...

    @abstractmethod
    def run_competition(self) -> Any: ...

    @abstractmethod
    def apply_economics(self) -> None: ...

    @abstractmethod
    def eliminate_dead(self) -> None: ...

    @abstractmethod
    def reproduce_winners(self) -> None: ...

    @abstractmethod
    def calculate_performance(self) -> None: ...
