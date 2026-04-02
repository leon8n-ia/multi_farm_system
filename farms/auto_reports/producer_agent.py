"""ProducerAgent for the AutoReports farm.

Uses a deterministic mock LLM (no real API) seeded on the agent's id so each
agent produces slightly different reports while remaining fully reproducible.
"""
import random
import time

from shared.models import Agent, TaskResult

_PERIODS = ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024", "Q1 2025"]
_SUMMARIES = [
    "Strong revenue growth driven by new customer acquisitions and product expansion.",
    "Steady performance with focus on operational efficiency and cost reduction.",
    "Mixed results with growth in core segments offset by macro headwinds.",
    "Exceptional quarter with record revenues and improved profit margins.",
    "Recovery trend confirmed; momentum building across key business units.",
]
_RISKS = [
    "Market volatility and rising interest rates pose short-term challenges.",
    "Supply chain disruptions continue to impact cost structures.",
    "Regulatory changes in key markets require strategic adaptation.",
    "Competitive pressure increasing in primary product segments.",
    "Currency fluctuations may affect international revenue reporting.",
]
_CONCLUSIONS = [
    "Management remains cautiously optimistic about full-year performance.",
    "Continued investment in R&D expected to drive future growth.",
    "Focus on cash generation and balance sheet strengthening.",
    "Strategic acquisitions pipeline remains active and selective.",
    "Board reaffirms guidance; operational milestones on track.",
]


def _generate_mock_report(topic: str, agent_id: str) -> str:
    rng = random.Random(hash(agent_id + topic))
    period = rng.choice(_PERIODS)
    summary = rng.choice(_SUMMARIES)
    risk = rng.choice(_RISKS)
    conclusion = rng.choice(_CONCLUSIONS)
    rev_growth = round(rng.uniform(-5.0, 25.0), 1)
    op_margin = round(rng.uniform(5.0, 30.0), 1)
    cash_flow = round(rng.uniform(100_000, 5_000_000))
    yoy = round(rng.uniform(-10.0, 40.0), 1)

    return (
        f"# Financial Report: {topic.title()} ({period})\n\n"
        f"## Executive Summary\n{summary}\n\n"
        f"## Key Metrics\n"
        f"- Revenue growth: {rev_growth}%\n"
        f"- Operating margin: {op_margin}%\n"
        f"- Cash flow: ${cash_flow:,.0f}\n"
        f"- Year-over-year change: {yoy}%\n\n"
        f"## Risk Analysis\n{risk}\n\n"
        f"## Conclusion\n{conclusion}\n"
    )


class ProducerAgent:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.last_output: str | None = None

    def execute_task(self, topic: str = "quarterly") -> TaskResult:
        start = time.perf_counter()
        report = _generate_mock_report(topic, self.agent.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        lines = report.splitlines()
        word_count = len(report.split())
        # Count heading lines (# / ##) as structural sections
        sections = sum(1 for ln in lines if ln.strip().startswith("#"))

        # quality: each of 5 expected sections contributes 18 pts; word count up to 10 pts
        quality_score = min(100.0, sections * 18.0 + min(10.0, word_count * 0.05))
        speed_score = max(0.0, 100.0 - elapsed_ms)
        resource_efficiency = min(100.0, word_count / 2.0)

        self.last_output = report
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {topic} report ({word_count} words, {sections} sections)",
            quality_score=quality_score,
            speed_score=speed_score,
            resource_efficiency=resource_efficiency,
        )
