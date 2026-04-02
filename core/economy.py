from shared.models import Agent, Farm
from config import (
    COST_OF_LIVING,
    COST_PER_ACTION,
    REWARD_WINNER,
    PENALTY_LOSER,
    REWARD_PER_USD_SOLD,
)


class EconomyEngine:
    def apply_cost_of_living(self, agent: Agent) -> None:
        agent.credits -= COST_OF_LIVING

    def apply_action_cost(self, agent: Agent) -> None:
        agent.credits -= COST_PER_ACTION

    def apply_winner_reward(self, agent: Agent) -> None:
        agent.credits += REWARD_WINNER

    def apply_loser_penalty(self, agent: Agent) -> None:
        agent.credits -= PENALTY_LOSER

    def apply_sale_reward(self, agent: Agent, usd_amount: float) -> None:
        agent.credits += usd_amount * REWARD_PER_USD_SOLD

    def calculate_roi(self, farm: Farm) -> float:
        if farm.capital_invested == 0:
            return 0.0
        return (farm.revenue - farm.expenses) / farm.capital_invested
