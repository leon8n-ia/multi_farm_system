import copy
import json
import logging
import os
import random

from config import COST_MUTATION
from shared.models import Agent

logger = logging.getLogger(__name__)

# Estimated USD cost per Claude API call (used for circuit-breaker pre-check)
ESTIMATED_COST_PER_CALL: float = 0.005

# Predefined option pools for string strategy keys
STRING_CHOICES: dict[str, list[str]] = {
    "primary_channel": ["gumroad", "etsy", "fiverr", "direct"],
    "pricing_model": ["fixed", "dynamic", "tiered"],
    "listing_quality": ["low", "medium", "high"],
    "target_audience": ["developers", "data_scientists", "analysts", "businesses"],
}

# Evolutionary bias towards high-value digital products for developers (2026)
NICHE_EVOLUTION_BIAS = """
El sistema está evolucionando hacia productos digitales
para desarrolladores. Productos de mayor valor en 2026:
- Boilerplates AI-ready para React/Next.js con configs
  para Claude/Cursor
- Prompt packs de 200-1200 prompts para Cursor, Copilot, Claude
- Workflow bundles CI/CD con prompts
- Cheat sheets técnicos Docker/AWS/K8s actualizados 2026
- Notion templates para dev teams
- Starter kits mobile AI-ready

Precio objetivo: $19-49 USD.
Audiencia: developers que usan Cursor, Claude Code, Copilot.

Si el agente puede derivar su output actual hacia alguno
de estos productos manteniendo coherencia con su granja,
priorizalo en la nueva estrategia.
Si no puede derivar (ej: granja de tráfico),
ignorá este contexto.
"""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CostCircuitBreaker:
    MAX_API_COST_PER_CYCLE: float = 2.0
    MAX_DAILY_COST: float = 10.0

    def __init__(self) -> None:
        self.cycle_cost: float = 0.0
        self.daily_cost: float = 0.0

    def can_proceed(self, estimated_cost: float) -> bool:
        return (
            self.cycle_cost + estimated_cost <= self.MAX_API_COST_PER_CYCLE
            and self.daily_cost + estimated_cost <= self.MAX_DAILY_COST
        )

    def record_spend(self, cost: float) -> None:
        self.cycle_cost += cost
        self.daily_cost += cost

    def reset_cycle(self) -> None:
        self.cycle_cost = 0.0


_default_breaker = CostCircuitBreaker()


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

def random_mutate(strategy: dict) -> dict:
    """Return a mutated copy of *strategy*: floats ±20%, strings swapped from pools."""
    result = copy.deepcopy(strategy)

    mutable = [
        k for k, v in result.items()
        if (isinstance(v, float) or (isinstance(v, int) and not isinstance(v, bool)))
        or (isinstance(v, str) and k in STRING_CHOICES)
    ]

    if not mutable:
        return result

    n = min(random.randint(1, 2), len(mutable))
    for key in random.sample(mutable, n):
        val = result[key]
        if isinstance(val, float):
            result[key] = max(0.01, round(val * random.uniform(0.8, 1.2), 4))
        elif isinstance(val, int):
            result[key] = max(1, round(val * random.uniform(0.8, 1.2)))
        elif isinstance(val, str):
            pool = [c for c in STRING_CHOICES[key] if c != val] or STRING_CHOICES[key]
            result[key] = random.choice(pool)

    return result


def _call_claude_api(agent: Agent, farm_context: dict, api_key: str) -> dict:
    """Call the Claude API and return the parsed strategy dict."""
    import anthropic

    history = farm_context.get("history", [])[-5:]
    context_without_history = {k: v for k, v in farm_context.items() if k != "history"}

    # Evolutionary bias prepended to guide mutations toward high-value products
    prompt = (
        f"{NICHE_EVOLUTION_BIAS}\n\n"
        f"Agent strategy:\n{json.dumps(agent.strategy, indent=2)}\n\n"
        f"Recent performance (last 5 results):\n{json.dumps(history, indent=2)}\n\n"
        f"Farm context:\n{json.dumps(context_without_history, indent=2)}\n\n"
        "Return an optimized strategy JSON."
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=(
            "You are a strategy optimizer for an AI agent in a multi-farm simulation. "
            "Respond ONLY with a valid JSON object containing the updated strategy. "
            "Use exactly the same keys as the current strategy. No explanation, no markdown."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(message.content[0].text)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def mutate_strategy(
    agent: Agent,
    farm_context: dict,
    circuit_breaker: CostCircuitBreaker | None = None,
) -> dict:
    """
    Attempt to mutate *agent.strategy* via the Claude API.

    Falls back to random_mutate when:
    - ANTHROPIC_API_KEY is not set, or
    - the circuit breaker has exhausted its budget, or
    - the API call / JSON parse fails.

    Always deducts COST_MUTATION from *agent.credits* and updates *agent.strategy*.
    Returns the new strategy dict.
    """
    cb = circuit_breaker or _default_breaker
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    new_strategy: dict | None = None

    if api_key and cb.can_proceed(ESTIMATED_COST_PER_CALL):
        try:
            new_strategy = _call_claude_api(agent, farm_context, api_key)
            cb.record_spend(ESTIMATED_COST_PER_CALL)
            logger.info("[mutator] Claude API mutation applied to agent %s", agent.id)
        except Exception as exc:
            logger.warning(
                "[mutator] API call failed (%s) — falling back to random_mutate", exc
            )

    if new_strategy is None:
        reason = "no API key" if not api_key else "circuit breaker / API error"
        logger.debug("[mutator] random_mutate fallback (%s) for agent %s", reason, agent.id)
        new_strategy = random_mutate(agent.strategy)

    agent.credits -= COST_MUTATION
    agent.strategy = new_strategy
    return new_strategy
