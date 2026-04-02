from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    REPRODUCING = "reproducing"


class FarmType(Enum):
    CROP = "crop"
    LIVESTOCK = "livestock"
    MIXED = "mixed"


@dataclass
class TaskResult:
    success: bool
    credits_earned: float
    description: str
    quality_score: float = 0.0
    speed_score: float = 0.0
    resource_efficiency: float = 0.0


@dataclass
class SaleResult:
    sold: bool
    usd_amount: float
    item: str


@dataclass
class Agent:
    id: str
    credits: float
    status: AgentStatus = AgentStatus.ALIVE
    actions_taken: int = 0
    # Competition metrics (reset each cycle)
    quality: float = 0.0
    speed: float = 0.0
    consistency: float = 0.0
    resource_efficiency: float = 0.0
    sold: bool = False
    # Lifecycle tracking
    cycles_without_profit: int = 0
    generation: int = 0
    parent_id: str | None = None
    strategy: dict = field(default_factory=dict)


@dataclass
class Farm:
    id: str
    farm_type: FarmType
    owner_id: str
    capital_invested: float
    revenue: float = 0.0
    expenses: float = 0.0
