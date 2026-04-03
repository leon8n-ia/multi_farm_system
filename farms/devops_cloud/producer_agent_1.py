"""DockerAgent — generates Docker workflow cheat sheets for DevOps engineers."""

import json
import logging
import os
import time
from typing import Any

from shared.models import Agent, TaskResult

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY: dict[str, Any] = {
    "niche_focus": "devops_cloud",
    "product_type": "cheat_sheet",
    "product_variant": "docker_workflow",
    "price_target": 24.0,
    "audience": "DevOps engineers and backend developers",
    "output_format": "markdown",
    "quality_threshold": 0.88,
    "items_per_pack": 50,
}

SYSTEM_PROMPT = """You are a senior DevOps engineer creating premium cheat sheets for DevOps engineers and backend developers.

Your task is to generate high-quality, production-ready cheat sheets that help developers:
- Master Docker, Kubernetes, and cloud infrastructure
- Implement CI/CD pipelines efficiently
- Follow security and performance best practices

Output format: JSON object with keys: title, description, content, price
- title: catchy product title (max 60 chars)
- description: compelling product description (max 200 chars)
- content: array of cheat sheet items, each with {category, command, description, example, tips}
- price: number (suggested price in USD)

Focus on practical, battle-tested commands and workflows. Include real-world examples."""


class DockerAgent:
    """Producer agent specialized in Docker/DevOps cheat sheets."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        if not agent.strategy:
            agent.strategy = dict(DEFAULT_STRATEGY)
        self.last_output: dict | None = None

    def execute_task(self, variant: str | None = None) -> TaskResult:
        """Generate a cheat sheet product using Claude API."""
        start = time.perf_counter()
        strategy = self.agent.strategy
        variant = variant or strategy.get("product_variant", "docker_workflow")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return self._fallback_generation(variant, start)

        try:
            product = self._generate_with_claude(variant, api_key)
            elapsed_ms = (time.perf_counter() - start) * 1000

            self.last_output = product
            quality_score = self._calculate_quality(product)
            speed_score = max(0.0, 100.0 - (elapsed_ms / 100))

            return TaskResult(
                success=True,
                credits_earned=0.0,
                description=f"Generated {variant} cheat sheet ({len(product.get('content', []))} items)",
                quality_score=quality_score,
                speed_score=speed_score,
                resource_efficiency=min(100.0, len(product.get("content", [])) / 2),
            )
        except Exception as exc:
            logger.warning("[DockerAgent] Claude API failed: %s — using fallback", exc)
            return self._fallback_generation(variant, start)

    def _generate_with_claude(self, variant: str, api_key: str) -> dict:
        """Call Claude API to generate product."""
        import anthropic

        strategy = self.agent.strategy
        items_per_pack = strategy.get("items_per_pack", 50)
        audience = strategy.get("audience", "DevOps engineers and backend developers")
        price_target = strategy.get("price_target", 24.0)

        user_prompt = f"""Generate a premium {variant.replace('_', ' ')} cheat sheet for {audience}.

Requirements:
- Product variant: {variant}
- Target items: {items_per_pack} commands/tips (generate at least 15 high-quality examples)
- Target price: ${price_target}
- Niche: DevOps/Cloud infrastructure

Generate a JSON object with: title, description, content (array of items), price.
Each item in content should have: category, command, description, example, tips."""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        return json.loads(response_text.strip())

    def _fallback_generation(self, variant: str, start_time: float) -> TaskResult:
        """Generate product without API (for testing/fallback)."""
        strategy = self.agent.strategy
        price = strategy.get("price_target", 24.0)

        self.last_output = {
            "title": f"DevOps {variant.replace('_', ' ').title()} Cheat Sheet",
            "description": f"Essential {variant.replace('_', ' ')} commands and workflows for DevOps engineers. Production-ready reference guide.",
            "content": [
                {
                    "category": "Container Basics",
                    "command": "docker run -d --name app -p 8080:80 nginx",
                    "description": "Run a detached container with port mapping",
                    "example": "Maps host port 8080 to container port 80",
                    "tips": "Use -d for background, --rm for auto-cleanup",
                },
                {
                    "category": "Image Management",
                    "command": "docker build -t myapp:v1 --no-cache .",
                    "description": "Build image without using cache",
                    "example": "Forces fresh build of all layers",
                    "tips": "Use --no-cache when dependencies change",
                },
                {
                    "category": "Debugging",
                    "command": "docker logs -f --tail 100 container_name",
                    "description": "Follow container logs with tail",
                    "example": "Shows last 100 lines and follows new output",
                    "tips": "Add --timestamps for debugging timing issues",
                },
            ],
            "price": price,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {variant} cheat sheet (fallback, 3 items)",
            quality_score=60.0,
            speed_score=max(0.0, 100.0 - elapsed_ms),
            resource_efficiency=30.0,
        )

    def _calculate_quality(self, product: dict) -> float:
        """Calculate quality score based on product completeness."""
        score = 0.0

        if product.get("title") and len(product["title"]) > 10:
            score += 20.0
        if product.get("description") and len(product["description"]) > 50:
            score += 20.0
        if product.get("price") and product["price"] > 0:
            score += 10.0

        content = product.get("content", [])
        if isinstance(content, list):
            item_count = len(content)
            score += min(40.0, item_count * 2.5)

            valid_items = sum(
                1 for item in content
                if isinstance(item, dict) and item.get("command") and item.get("description")
            )
            score += min(10.0, valid_items * 0.5)

        return min(100.0, score)
