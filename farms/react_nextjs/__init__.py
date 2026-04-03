"""React/Next.js Farm — generates developer-focused prompt packs."""

from farms.react_nextjs.farm import ReactNextjsFarm
from farms.react_nextjs.producer_agent_1 import PromptPackAgent

__all__ = [
    "ReactNextjsFarm",
    "PromptPackAgent",
]
