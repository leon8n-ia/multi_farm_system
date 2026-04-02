"""ProducerAgent for the MonetizedContent farm.

Generates a short article/newsletter with title, intro, 3 key points and a
conclusion.  Niche rotates through: tech, finance, health.
"""
import random
import time

from shared.models import Agent, TaskResult

_CONTENT: dict[str, dict] = {
    "tech": {
        "titles": [
            "5 AI Tools Transforming Productivity in 2025",
            "Why Python Dominates Modern Data Science",
            "The Rise of Edge Computing: What You Need to Know",
            "Cybersecurity Essentials for Remote Teams",
        ],
        "intro": "Technology continues to reshape how we work, communicate, and create value.",
        "points": [
            ("Automation & AI", "Machine learning tools now handle repetitive workflows, freeing teams for creative work."),
            ("Cloud-Native Development", "Serverless architectures reduce infrastructure overhead and scale on demand."),
            ("Open-Source Ecosystems", "Community-driven projects accelerate innovation across every tech stack."),
            ("Data Privacy", "Modern regulations push organisations toward privacy-by-design architecture."),
        ],
        "conclusion": "Staying ahead means embracing change, continuous learning, and pragmatic tool adoption.",
    },
    "finance": {
        "titles": [
            "3 Wealth-Building Habits High Earners Share",
            "Understanding Dollar-Cost Averaging for Beginners",
            "How Inflation Silently Erodes Your Savings",
            "Index Funds vs Active Management: The Numbers",
        ],
        "intro": "Financial literacy is the foundation of long-term wealth and security.",
        "points": [
            ("Compound Interest", "Starting early maximises compounding — even small contributions grow dramatically over decades."),
            ("Diversification", "Spreading risk across asset classes reduces volatility without sacrificing returns."),
            ("Expense Ratios", "Low-cost index funds consistently outperform high-fee managed funds over 10+ year horizons."),
            ("Emergency Fund", "A six-month cash reserve prevents forced selling during market downturns."),
        ],
        "conclusion": "Consistent, disciplined saving combined with low-cost investing beats market timing every time.",
    },
    "health": {
        "titles": [
            "The Science Behind Quality Sleep and Performance",
            "Zone 2 Cardio: The Overlooked Fitness Cornerstone",
            "Gut Health and Its Surprising Effect on Mood",
            "Intermittent Fasting: Evidence vs Hype",
        ],
        "intro": "Small, sustainable habits compound into dramatic health improvements over time.",
        "points": [
            ("Sleep Consistency", "Going to bed at the same time each night stabilises circadian rhythms and improves cognitive function."),
            ("Strength Training", "Resistance exercise preserves muscle mass, boosts metabolism, and improves insulin sensitivity."),
            ("Nutrition Basics", "Whole foods, adequate protein, and minimising ultra-processed items covers 80% of optimal nutrition."),
            ("Stress Management", "Chronic stress elevates cortisol, undermining both physical and mental health markers."),
        ],
        "conclusion": "Optimising sleep, movement, and nutrition creates a foundation that elevates every other area of life.",
    },
}

NICHES = list(_CONTENT.keys())


def _generate_article(niche: str, agent_id: str) -> str:
    niche = niche if niche in _CONTENT else "tech"
    data = _CONTENT[niche]
    rng = random.Random(hash(agent_id + niche))
    title = rng.choice(data["titles"])
    points = rng.sample(data["points"], k=3)

    lines = [
        f"# {title}",
        "",
        "## Introduction",
        data["intro"],
        "",
        "## Key Points",
        "",
    ]
    for i, (heading, detail) in enumerate(points, 1):
        lines.append(f"**Point {i}: {heading}**")
        lines.append(detail)
        lines.append("")

    lines += ["## Conclusion", data["conclusion"], ""]
    return "\n".join(lines)


class ProducerAgent:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.last_output: str | None = None

    def execute_task(self, niche: str = "tech") -> TaskResult:
        start = time.perf_counter()
        article = _generate_article(niche, self.agent.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        lines = article.splitlines()
        word_count = len(article.split())

        has_title = any(ln.startswith("# ") for ln in lines)
        has_intro = any("Introduction" in ln for ln in lines)
        key_points = sum(1 for ln in lines if ln.startswith("**Point"))
        has_conclusion = any("Conclusion" in ln for ln in lines)

        structure_score = (has_title + has_intro + (key_points >= 3) + has_conclusion) * 22.0
        length_bonus = min(12.0, word_count * 0.05)
        quality_score = min(100.0, structure_score + length_bonus)
        speed_score = max(0.0, 100.0 - elapsed_ms)
        resource_efficiency = min(100.0, word_count / 2.0)

        self.last_output = article
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {niche} article ({word_count} words)",
            quality_score=quality_score,
            speed_score=speed_score,
            resource_efficiency=resource_efficiency,
        )
