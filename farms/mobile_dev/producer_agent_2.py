"""FlutterAgent — generates Flutter starter kits for mobile developers."""

import json
import logging
import os
import time
from typing import Any

from shared.models import Agent, TaskResult

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY: dict[str, Any] = {
    "niche_focus": "mobile_dev",
    "product_type": "starter_kit",
    "product_variant": "flutter_starter",
    "price_target": 34.0,
    "audience": "Flutter developers using AI tools",
    "output_format": "markdown",
    "quality_threshold": 0.88,
    "items_per_pack": 150,
}

SYSTEM_PROMPT = """You are a senior Flutter developer creating premium Flutter starter kits for developers using AI tools.

Your task is to generate high-quality, production-ready starter kit components that help developers:
- Build Flutter apps with AI integrations (OpenAI, Claude, local LLMs)
- Implement best practices for cross-platform mobile AI applications
- Ship faster with ready-to-use widgets, providers, and utilities

Output format: JSON object with keys: title, description, content, price
- title: catchy product title (max 60 chars)
- description: compelling product description (max 200 chars)
- content: array of starter kit items, each with {category, name, description, code_snippet, usage_example, tips}
- price: number (suggested price in USD)

Focus on practical, production-ready Dart/Flutter code. Include real-world examples and common use cases."""


class FlutterAgent:
    """Producer agent specialized in Flutter AI starter kits."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        if not agent.strategy:
            agent.strategy = dict(DEFAULT_STRATEGY)
        self.last_output: dict | None = None

    def execute_task(self, variant: str | None = None) -> TaskResult:
        """Generate a Flutter starter kit product using Claude API."""
        start = time.perf_counter()
        strategy = self.agent.strategy
        variant = variant or strategy.get("product_variant", "flutter_starter")

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
                description=f"Generated {variant} starter kit ({len(product.get('content', []))} items)",
                quality_score=quality_score,
                speed_score=speed_score,
                resource_efficiency=min(100.0, len(product.get("content", [])) / 2),
            )
        except Exception as exc:
            logger.warning("[FlutterAgent] Claude API failed: %s — using fallback", exc)
            return self._fallback_generation(variant, start)

    def _generate_with_claude(self, variant: str, api_key: str) -> dict:
        """Call Claude API to generate product."""
        import anthropic

        strategy = self.agent.strategy
        items_per_pack = strategy.get("items_per_pack", 150)
        audience = strategy.get("audience", "Flutter developers using AI tools")
        price_target = strategy.get("price_target", 34.0)

        user_prompt = f"""Generate a premium {variant.replace('_', ' ')} starter kit for {audience}.

Requirements:
- Product variant: {variant}
- Target items: {items_per_pack} components/widgets (generate at least 20 high-quality examples)
- Target price: ${price_target}
- Niche: Flutter mobile development with AI integrations

Generate a JSON object with: title, description, content (array of items), price.
Each item in content should have: category, name, description, code_snippet, usage_example, tips."""

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
            "title": f"Flutter AI {variant.replace('_', ' ').title()} Kit",
            "description": f"Production-ready {variant.replace('_', ' ')} widgets and utilities for Flutter developers building AI-powered apps.",
            "content": [
                {
                    "category": "AI Integration",
                    "name": "ClaudeChatProvider",
                    "description": "Provider for Claude API chat completions with state management",
                    "code_snippet": "final chat = context.watch<ClaudeChatProvider>();",
                    "usage_example": "Wrap your app with ChangeNotifierProvider and access chat state anywhere",
                    "tips": "Use streaming for better UX on mobile devices",
                },
                {
                    "category": "AI Integration",
                    "name": "AIResponseWidget",
                    "description": "Styled widget for AI responses with markdown support",
                    "code_snippet": "AIResponseWidget(response: aiResponse, showCopyButton: true)",
                    "usage_example": "Display AI responses with proper formatting and copy functionality",
                    "tips": "Enable syntax highlighting for code blocks with flutter_highlight",
                },
                {
                    "category": "Utilities",
                    "name": "TokenEstimator",
                    "description": "Utility class to estimate token count before API calls",
                    "code_snippet": "final tokens = TokenEstimator.estimate(prompt);",
                    "usage_example": "Check token count before sending to avoid API limits",
                    "tips": "Cache results for repeated prompts using compute isolate",
                },
            ],
            "price": price,
        }

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return TaskResult(
            success=True,
            credits_earned=0.0,
            description=f"Generated {variant} starter kit (fallback, 3 items)",
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
                if isinstance(item, dict) and item.get("name") and item.get("description")
            )
            score += min(10.0, valid_items * 0.5)

        return min(100.0, score)
