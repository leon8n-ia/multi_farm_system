from typing import List

from config import NO_PROFIT_THRESHOLD, PENALTY_LOSER
from core.economy import EconomyEngine
from shared.models import Agent


def calculate_agent_score(agent: Agent) -> float:
    """Weighted score: quality(40%) + speed(20%) + consistency(20%) + resource_efficiency(20%) + sold_boost(+100)."""
    score = (
        agent.quality * 0.4
        + agent.speed * 0.2
        + agent.consistency * 0.2
        + agent.resource_efficiency * 0.2
    )
    if agent.sold:
        score += 100.0
    return score


def run_competition(agents: List[Agent], economy: EconomyEngine) -> Agent:
    """
    Score all agents, reward the winner and penalise losers.
    Also applies escalating temporal pressure to any agent whose
    cycles_without_profit has reached NO_PROFIT_THRESHOLD.
    Returns the winning Agent.
    """
    if not agents:
        raise ValueError("Cannot run competition with no agents")

    winner = max(agents, key=calculate_agent_score)

    for agent in agents:
        if agent is winner:
            economy.apply_winner_reward(agent)
        else:
            economy.apply_loser_penalty(agent)

        # Temporal pressure: escalates linearly beyond the threshold
        if agent.cycles_without_profit >= NO_PROFIT_THRESHOLD:
            pressure = agent.cycles_without_profit - NO_PROFIT_THRESHOLD + 1
            agent.credits -= PENALTY_LOSER * pressure

    return winner
