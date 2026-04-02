"""ProducerAgent for the ProductListing farm.

Generates an optimised marketplace listing (title, description, price, tags)
for a given product name.  No external API is used.
"""
import random
import time

from shared.models import Agent, TaskResult

_ADJECTIVES = ["Premium", "Professional", "Essential", "Advanced", "Complete", "Ultimate"]
_PLATFORMS = ["shopify", "amazon", "etsy", "ebay", "woocommerce"]
_TAGS_POOL = [
    "digital", "download", "template", "professional", "instant",
    "quality", "value", "best-seller", "top-rated", "exclusive",
]
_DESC_PHRASES = [
    "Includes detailed documentation and lifetime updates.",
    "Optimized for maximum results and ease of use.",
    "Trusted by thousands of professionals worldwide.",
    "Ready to use out of the box with step-by-step guidance.",
    "Compatible with all major platforms and devices.",
]


def _generate_listing(product_name: str, agent_id: str) -> dict:
    rng = random.Random(hash(agent_id + product_name))
    adj = rng.choice(_ADJECTIVES)
    title = f"{adj} {product_name.replace('-', ' ').title()}"
    phrases = rng.sample(_DESC_PHRASES, k=2)
    description = f"High-quality {product_name} for professionals. " + " ".join(phrases)
    price = round(rng.uniform(4.99, 49.99), 2)
    tags = rng.sample(_TAGS_POOL, k=5)
    platform = rng.choice(_PLATFORMS)
    return {
        "title": title,
        "description": description,
        "price": price,
        "tags": tags,
        "platform": platform,
    }


def _score_listing(listing: dict) -> float:
    score = 0.0
    if listing.get("title"):
        score += 20.0
    if len(listing.get("description", "")) > 50:
        score += 30.0
    score += min(30.0, len(listing.get("tags", [])) * 6.0)
    if listing.get("price", 0) > 0:
        score += 20.0
    return min(100.0, score)


class ProducerAgent:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.last_output: dict | None = None

    def execute_task(self, product_name: str = "digital-product") -> TaskResult:
        start = time.perf_counter()
        listing = _generate_listing(product_name, self.agent.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        quality_score = _score_listing(listing)
        speed_score = max(0.0, 100.0 - elapsed_ms)
        resource_efficiency = min(100.0, len(str(listing)) / 10.0)

        self.last_output = listing
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated listing: '{listing['title']}' @ ${listing['price']}",
            quality_score=quality_score,
            speed_score=speed_score,
            resource_efficiency=resource_efficiency,
        )
