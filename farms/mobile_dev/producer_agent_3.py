"""MobilePromptsAgent — generates mobile development prompt packs for Cursor and Claude users."""

import json
import logging
import os
import time
from typing import Any

from shared.models import Agent, TaskResult

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY: dict[str, Any] = {
    "niche_focus": "mobile_dev",
    "product_type": "prompt_pack",
    "product_variant": "mobile_prompts",
    "price_target": 34.0,
    "audience": "mobile developers using Cursor and Claude",
    "output_format": "markdown",
    "quality_threshold": 0.88,
    "items_per_pack": 150,
}

SYSTEM_PROMPT = """You are a senior mobile developer creating premium prompt packs for developers using Cursor and Claude.

Your task is to generate high-quality, battle-tested prompts that help mobile developers:
- Build React Native and Flutter apps faster with AI assistance
- Debug complex mobile issues efficiently
- Generate production-ready components and utilities
- Implement best practices for mobile development

Output format: JSON object with keys: title, description, content, price
- title: catchy product title (max 60 chars)
- description: compelling product description (max 200 chars)
- content: array of prompt items, each with {category, prompt_name, prompt_template, use_case, example_output, tips}
- price: number (suggested price in USD)

Focus on practical prompts that solve real mobile development problems. Include context and examples."""


class MobilePromptsAgent:
    """Producer agent specialized in mobile development prompt packs."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        if not agent.strategy:
            agent.strategy = dict(DEFAULT_STRATEGY)
        self.last_output: dict | None = None

    def execute_task(self, variant: str | None = None) -> TaskResult:
        """Generate a mobile prompt pack product using Claude API."""
        start = time.perf_counter()
        strategy = self.agent.strategy
        variant = variant or strategy.get("product_variant", "mobile_prompts")

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
                description=f"Generated {variant} prompt pack ({len(product.get('content', []))} items)",
                quality_score=quality_score,
                speed_score=speed_score,
                resource_efficiency=min(100.0, len(product.get("content", [])) / 2),
            )
        except Exception as exc:
            logger.warning("[MobilePromptsAgent] Claude API failed: %s — using fallback", exc)
            return self._fallback_generation(variant, start)

    def _generate_with_claude(self, variant: str, api_key: str) -> dict:
        """Call Claude API to generate product."""
        import anthropic

        strategy = self.agent.strategy
        items_per_pack = strategy.get("items_per_pack", 150)
        audience = strategy.get("audience", "mobile developers using Cursor and Claude")
        price_target = strategy.get("price_target", 34.0)

        user_prompt = f"""Generate a premium {variant.replace('_', ' ')} prompt pack for {audience}.

Requirements:
- Product variant: {variant}
- Target items: {items_per_pack} prompts (generate at least 20 high-quality examples)
- Target price: ${price_target}
- Niche: Mobile development prompts for AI coding assistants

Generate a JSON object with: title, description, content (array of items), price.
Each item in content should have: category, prompt_name, prompt_template, use_case, example_output, tips."""

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
        price = strategy.get("price_target", 34.0)

        self.last_output = {
            "title": f"Mobile Dev {variant.replace('_', ' ').title()} Pack",
            "description": f"Battle-tested {variant.replace('_', ' ')} for mobile developers using Cursor and Claude to build apps faster.",
            "content": [
                {
                    "category": "Component Generation",
                    "prompt_name": "React Native Screen Generator",
                    "prompt_template": "Create a production-ready React Native screen for [FEATURE] with: TypeScript, proper navigation typing, loading/error states, and accessibility labels.",
                    "use_case": "Quickly scaffold new screens with best practices",
                    "example_output": "Full screen component with hooks, styles, and proper typing",
                    "tips": "Add specific UI library (e.g., 'using React Native Paper') for consistent styling",
                },
                {
                    "category": "Debugging",
                    "prompt_name": "Mobile Crash Analyzer",
                    "prompt_template": "Analyze this mobile crash log and provide: 1) Root cause, 2) Affected code path, 3) Fix with code example, 4) Prevention strategy. Crash: [PASTE_LOG]",
                    "use_case": "Debug crashes from production or development",
                    "example_output": "Detailed analysis with actionable fix and prevention tips",
                    "tips": "Include device info and OS version for platform-specific issues",
                },
                {
                    "category": "Performance",
                    "prompt_name": "Mobile Performance Audit",
                    "prompt_template": "Audit this mobile component for performance issues. Check for: unnecessary re-renders, memory leaks, heavy computations on main thread, and suggest optimizations. Code: [PASTE_CODE]",
                    "use_case": "Optimize slow or janky mobile UI",
                    "example_output": "List of issues with priority and optimized code snippets",
                    "tips": "Mention target FPS (60fps) and specific performance metrics",
                },
            ],
            "price": price,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {variant} prompt pack (fallback, 3 items)",
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
            score += min(40.0, item_count * 2.0)

            valid_items = sum(
                1 for item in content
                if isinstance(item, dict) and item.get("prompt_name") and item.get("prompt_template")
            )
            score += min(10.0, valid_items * 0.5)

        return min(100.0, score)
