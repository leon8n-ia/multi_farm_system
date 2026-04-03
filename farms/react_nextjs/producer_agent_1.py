"""PromptPackAgent — generates React/Next.js prompt packs for developers using Cursor and Claude."""

import json
import logging
import os
import time
from typing import Any

from shared.models import Agent, TaskResult

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY: dict[str, Any] = {
    "niche_focus": "react_nextjs",
    "product_type": "prompt_pack",
    "product_variant": "cursor_prompts",
    "price_target": 39.0,
    "audience": "developers using Cursor and Claude",
    "output_format": "markdown",
    "quality_threshold": 0.90,
    "items_per_pack": 200,
}

SYSTEM_PROMPT = """You are a senior React/Next.js developer creating premium prompt packs for developers who use Cursor IDE and Claude AI.

Your task is to generate high-quality, production-ready prompts that help developers:
- Build React/Next.js applications faster
- Write cleaner, more maintainable code
- Leverage AI assistants effectively

Output format: JSON object with keys: title, description, content, price
- title: catchy product title (max 60 chars)
- description: compelling product description (max 200 chars)
- content: array of prompt objects, each with {category, prompt_name, prompt_text, use_case}
- price: number (suggested price in USD)

Focus on practical, immediately usable prompts. No fluff."""


class PromptPackAgent:
    """Producer agent specialized in React/Next.js prompt packs."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        if not agent.strategy:
            agent.strategy = dict(DEFAULT_STRATEGY)
        self.last_output: dict | None = None

    def execute_task(self, variant: str | None = None) -> TaskResult:
        """Generate a prompt pack product using Claude API."""
        start = time.perf_counter()
        strategy = self.agent.strategy
        variant = variant or strategy.get("product_variant", "cursor_prompts")

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
                description=f"Generated {variant} prompt pack ({len(product.get('content', []))} prompts)",
                quality_score=quality_score,
                speed_score=speed_score,
                resource_efficiency=min(100.0, len(product.get("content", [])) / 2),
            )
        except Exception as exc:
            logger.warning("[PromptPackAgent] Claude API failed: %s — using fallback", exc)
            return self._fallback_generation(variant, start)

    def _generate_with_claude(self, variant: str, api_key: str) -> dict:
        """Call Claude API to generate product."""
        import anthropic

        strategy = self.agent.strategy
        items_per_pack = strategy.get("items_per_pack", 200)
        audience = strategy.get("audience", "developers using Cursor and Claude")
        price_target = strategy.get("price_target", 39.0)

        user_prompt = f"""Generate a premium {variant.replace('_', ' ')} prompt pack for {audience}.

Requirements:
- Product variant: {variant}
- Target items: {items_per_pack} prompts (generate at least 15 high-quality examples)
- Target price: ${price_target}
- Niche: React/Next.js development

Generate a JSON object with: title, description, content (array of prompts), price.
Each prompt in content should have: category, prompt_name, prompt_text, use_case."""

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
        price = strategy.get("price_target", 39.0)

        self.last_output = {
            "title": f"React/Next.js {variant.replace('_', ' ').title()} Pack",
            "description": f"Premium {variant.replace('_', ' ')} for developers using Cursor and Claude. Boost your productivity with AI-ready prompts.",
            "content": [
                {
                    "category": "Components",
                    "prompt_name": "Create React Component",
                    "prompt_text": "Create a TypeScript React functional component with proper typing, hooks, and error boundaries.",
                    "use_case": "Quick component scaffolding",
                },
                {
                    "category": "Hooks",
                    "prompt_name": "Custom Hook Generator",
                    "prompt_text": "Generate a custom React hook that handles [state/effect] with proper cleanup and TypeScript types.",
                    "use_case": "Reusable logic extraction",
                },
                {
                    "category": "Next.js",
                    "prompt_name": "API Route Handler",
                    "prompt_text": "Create a Next.js API route with input validation, error handling, and proper HTTP methods.",
                    "use_case": "Backend API development",
                },
            ],
            "price": price,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {variant} prompt pack (fallback, 3 prompts)",
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
            prompt_count = len(content)
            score += min(40.0, prompt_count * 2.5)

            valid_prompts = sum(
                1 for p in content
                if isinstance(p, dict) and p.get("prompt_text") and p.get("prompt_name")
            )
            score += min(10.0, valid_prompts * 0.5)

        return min(100.0, score)
