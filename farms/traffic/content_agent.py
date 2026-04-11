"""Reddit content agent: generates organic Reddit posts promoting farm products.

Supports farm-specific content generation with appropriate subreddits,
product descriptions, and Gumroad links per farm type.

Falls back to simulation when ANTHROPIC_API_KEY is absent or the API call fails.
"""
import json
import logging
import os
import random

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Farm-specific configuration
# ---------------------------------------------------------------------------

FARM_CONFIG: dict[str, dict] = {
    "data_cleaning": {
        "subreddits": ["datasets", "MachineLearning"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "cleaned dataset",
        "niches": ["ecommerce", "fintech", "saas"],
        "audience": "data scientists and ML engineers",
    },
    "auto_reports": {
        "subreddits": ["datascience", "investing"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "automated financial report",
        "niches": ["crypto", "saas metrics", "trading"],
        "audience": "analysts and investors",
    },
    "product_listing": {
        "subreddits": ["ecommerce", "Entrepreneur"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "optimized product listing",
        "niches": ["mercadolibre", "amazon", "ecommerce"],
        "audience": "ecommerce sellers",
    },
    "monetized_content": {
        "subreddits": ["Python", "learnprogramming"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "developer article pack",
        "niches": ["python automation", "ai tools", "scripting"],
        "audience": "developers learning automation",
    },
    "react_nextjs": {
        "subreddits": ["reactjs", "webdev"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "React/Next.js prompt pack",
        "niches": ["cursor prompts", "claude prompts", "boilerplates"],
        "audience": "React developers using AI tools",
    },
    "devops_cloud": {
        "subreddits": ["devops", "aws"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "DevOps cheat sheet",
        "niches": ["docker", "aws", "kubernetes"],
        "audience": "DevOps engineers and cloud architects",
    },
    "mobile_dev": {
        "subreddits": ["reactnative", "FlutterDev"],
        "gumroad_url": "https://leon8n-ia.github.io/multi_farm_system/",
        "product_type": "mobile starter kit",
        "niches": ["react native", "flutter", "mobile ai"],
        "audience": "mobile developers using AI tools",
    },
}

# Default subreddits (fallback)
SUBREDDITS = [
    "datasets",
    "datascience",
    "MachineLearning",
    "learnmachinelearning",
]

_STYLES = [
    "recurso gratuito",
    "tip técnico",
    "showcase de producto",
    "pregunta con respuesta",
]

# ---------------------------------------------------------------------------
# Farm-specific simulation posts
# ---------------------------------------------------------------------------

_SIMULATION_POSTS_BY_FARM: dict[str, list[dict]] = {
    "data_cleaning": [
        {
            "title": "[Resource] Clean e-commerce dataset — 10k products, normalized and deduped",
            "body": (
                "Sharing a cleaned e-commerce dataset I prepared for ML projects:\n\n"
                "- 10,000 product records\n"
                "- Normalized category labels\n"
                "- Price outliers removed (>3σ)\n"
                "- Duplicate records deduplicated\n"
                "- UTF-8 encoded, ready for pandas\n\n"
                "Great baseline for recommendation systems or price-prediction models.\n\n"
                "Download: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "datasets",
            "score_estimado": 78,
            "style": "recurso gratuito",
        },
        {
            "title": "Cleaned fintech transaction dataset — 50k rows, fraud labels included",
            "body": (
                "For anyone working on fraud detection:\n\n"
                "- 50,000 transaction records\n"
                "- Binary fraud labels (verified)\n"
                "- Normalized amounts and timestamps\n"
                "- No PII, synthetic merchant IDs\n\n"
                "Useful for training classifiers or benchmarking models.\n\n"
                "Link: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "MachineLearning",
            "score_estimado": 72,
            "style": "showcase de producto",
        },
        {
            "title": "SaaS metrics dataset — MRR, churn, LTV for 200 companies",
            "body": (
                "Cleaned dataset of SaaS metrics for benchmarking:\n\n"
                "- 200 anonymized companies\n"
                "- Monthly MRR, churn rate, CAC, LTV\n"
                "- 24 months of data per company\n"
                "- Outliers flagged, missing values imputed\n\n"
                "Perfect for SaaS analytics projects.\n\n"
                "Get it: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "datascience",
            "score_estimado": 68,
            "style": "tip técnico",
        },
    ],
    "auto_reports": [
        {
            "title": "Automated crypto portfolio report — Python script + template",
            "body": (
                "Built an automated reporting system for crypto portfolios:\n\n"
                "- Pulls data from CoinGecko API\n"
                "- Calculates daily/weekly/monthly returns\n"
                "- Generates PDF report with charts\n"
                "- Includes risk metrics (Sharpe, volatility)\n\n"
                "Template + script available for customization.\n\n"
                "Check it out: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "investing",
            "score_estimado": 65,
            "style": "showcase de producto",
        },
        {
            "title": "SaaS metrics dashboard template — auto-updates from Stripe",
            "body": (
                "Sharing a reporting template I use for SaaS metrics:\n\n"
                "- Connects to Stripe API\n"
                "- Auto-calculates MRR, churn, LTV\n"
                "- Weekly email reports\n"
                "- Google Sheets + Python integration\n\n"
                "Saves hours of manual reporting.\n\n"
                "Template: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "datascience",
            "score_estimado": 71,
            "style": "recurso gratuito",
        },
    ],
    "product_listing": [
        {
            "title": "Optimized MercadoLibre listing templates — tested with 500+ products",
            "body": (
                "After A/B testing 500+ product listings on MercadoLibre:\n\n"
                "**What works:**\n"
                "- Title: brand + model + key feature + benefit\n"
                "- 7-10 bullet points, front-loaded keywords\n"
                "- Price ending in 9 or 7\n"
                "- First image: product on white background\n\n"
                "Templates with examples for each category.\n\n"
                "Get them: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "ecommerce",
            "score_estimado": 74,
            "style": "tip técnico",
        },
        {
            "title": "E-commerce listing optimizer — AI-powered title and description generator",
            "body": (
                "Built a tool that optimizes product listings:\n\n"
                "- Input: basic product info\n"
                "- Output: SEO-optimized title, bullets, description\n"
                "- Works for Amazon, MercadoLibre, Shopify\n"
                "- Includes keyword research data\n\n"
                "Increased CTR by 23% in our tests.\n\n"
                "Try it: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "Entrepreneur",
            "score_estimado": 69,
            "style": "showcase de producto",
        },
    ],
    "monetized_content": [
        {
            "title": "Python automation scripts for developers — 50+ ready-to-use scripts",
            "body": (
                "Compiled my favorite Python automation scripts:\n\n"
                "- File organization and renaming\n"
                "- API data fetching and caching\n"
                "- PDF/Excel report generation\n"
                "- Slack/Discord notifications\n"
                "- Database backup automation\n\n"
                "All scripts documented with examples.\n\n"
                "Collection: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "Python",
            "score_estimado": 76,
            "style": "recurso gratuito",
        },
        {
            "title": "AI automation workflows — integrate Claude/GPT into your Python scripts",
            "body": (
                "Guide to adding AI to your automation:\n\n"
                "- Claude API integration patterns\n"
                "- GPT function calling examples\n"
                "- Cost optimization strategies\n"
                "- Error handling and retries\n"
                "- Real-world use cases\n\n"
                "Includes 20+ working code examples.\n\n"
                "Get it: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "learnprogramming",
            "score_estimado": 72,
            "style": "tip técnico",
        },
    ],
    "react_nextjs": [
        {
            "title": "200+ Cursor prompts for React/Next.js — tested and optimized",
            "body": (
                "Compiled my most effective Cursor prompts for React development:\n\n"
                "- Component generation (50+ prompts)\n"
                "- Hook patterns and custom hooks\n"
                "- Next.js App Router patterns\n"
                "- Testing with Vitest/RTL\n"
                "- TypeScript type generation\n\n"
                "Each prompt tested on real projects.\n\n"
                "Get them: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "reactjs",
            "score_estimado": 82,
            "style": "recurso gratuito",
        },
        {
            "title": "Next.js 14 boilerplate with Claude Code integration — AI-ready starter",
            "body": (
                "Built a Next.js starter optimized for AI-assisted development:\n\n"
                "- App Router + TypeScript\n"
                "- Tailwind + shadcn/ui\n"
                "- Claude Code .cursorrules included\n"
                "- Auth, DB, API routes pre-configured\n"
                "- 100+ prompts for common tasks\n\n"
                "Ship faster with AI.\n\n"
                "Starter: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "webdev",
            "score_estimado": 79,
            "style": "showcase de producto",
        },
    ],
    "devops_cloud": [
        {
            "title": "Docker cheat sheet 2026 — commands, Compose, best practices",
            "body": (
                "Updated Docker cheat sheet for 2026:\n\n"
                "- Essential CLI commands\n"
                "- Multi-stage build patterns\n"
                "- Compose v2 examples\n"
                "- Security best practices\n"
                "- Debugging containers\n\n"
                "PDF + Markdown versions included.\n\n"
                "Download: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "devops",
            "score_estimado": 85,
            "style": "recurso gratuito",
        },
        {
            "title": "AWS + Terraform cheat sheet — IaC patterns for production",
            "body": (
                "Compiled AWS/Terraform patterns I use daily:\n\n"
                "- VPC, ECS, RDS modules\n"
                "- IAM policy templates\n"
                "- Cost optimization configs\n"
                "- CI/CD with GitHub Actions\n"
                "- Monitoring with CloudWatch\n\n"
                "Battle-tested in production.\n\n"
                "Get it: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "aws",
            "score_estimado": 78,
            "style": "tip técnico",
        },
        {
            "title": "Kubernetes cheat sheet — kubectl, Helm, debugging",
            "body": (
                "K8s reference I keep open daily:\n\n"
                "- kubectl commands by category\n"
                "- Helm chart patterns\n"
                "- Debugging pods and services\n"
                "- Resource limits and requests\n"
                "- RBAC quick reference\n\n"
                "Print-friendly PDF.\n\n"
                "Download: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "devops",
            "score_estimado": 81,
            "style": "showcase de producto",
        },
    ],
    "mobile_dev": [
        {
            "title": "React Native AI starter kit — Claude + Expo + TypeScript",
            "body": (
                "Built a React Native starter for AI-powered apps:\n\n"
                "- Expo SDK 52 + TypeScript\n"
                "- Claude API integration\n"
                "- Chat UI components\n"
                "- Voice input support\n"
                "- 50+ Cursor prompts included\n\n"
                "Ship mobile AI apps faster.\n\n"
                "Starter: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "reactnative",
            "score_estimado": 77,
            "style": "recurso gratuito",
        },
        {
            "title": "Flutter AI toolkit — prompts and widgets for AI features",
            "body": (
                "Toolkit for adding AI to Flutter apps:\n\n"
                "- Pre-built chat widgets\n"
                "- OpenAI/Claude service classes\n"
                "- Streaming response handling\n"
                "- Offline caching patterns\n"
                "- Cursor prompts for Flutter\n\n"
                "Works with GPT-4 and Claude.\n\n"
                "Get it: https://leon8n-ia.github.io/multi_farm_system/\n\n"
                "Join our Discord community: https://discord.gg/cWfaKUtgSB"
            ),
            "subreddit": "FlutterDev",
            "score_estimado": 74,
            "style": "showcase de producto",
        },
    ],
}

# Fallback generic posts
_SIMULATION_POSTS_GENERIC = [
    {
        "title": "[Resource] Free cleaned dataset — ready for ML projects",
        "body": (
            "Sharing a cleaned dataset for the community:\n\n"
            "- Normalized and deduplicated\n"
            "- Missing values handled\n"
            "- UTF-8 encoded\n\n"
            "Great for learning and prototyping."
        ),
        "subreddit": "datascience",
        "score_estimado": 65,
        "style": "recurso gratuito",
    },
]

# ---------------------------------------------------------------------------
# Farm-specific simulation tweets
# ---------------------------------------------------------------------------

_SIMULATION_TWEETS_BY_FARM: dict[str, list[str]] = {
    "data_cleaning": [
        "Just released a clean e-commerce dataset: 10k products, normalized labels, outliers removed. Perfect for recommendation systems. #DataScience #MachineLearning",
        "Fintech transaction data for fraud detection — 50k rows, clean and labeled. Link in bio. #ML #FraudDetection #datasets",
    ],
    "auto_reports": [
        "Automated crypto portfolio reports with Python — pulls data, calculates metrics, generates PDF. Template available. #crypto #Python #automation",
        "SaaS metrics dashboard that auto-updates from Stripe. MRR, churn, LTV calculated automatically. #SaaS #analytics",
    ],
    "product_listing": [
        "A/B tested 500+ MercadoLibre listings. Key insight: titles with brand + model + benefit convert 23% better. #ecommerce #optimization",
        "AI-powered listing optimizer for Amazon/MercadoLibre. Input product info, get SEO-optimized copy. #ecommerce #AI",
    ],
    "monetized_content": [
        "50+ Python automation scripts: file org, API fetching, report generation, notifications. All documented. #Python #automation",
        "Guide to integrating Claude/GPT into Python scripts. 20+ working examples included. #AI #Python #automation",
    ],
    "react_nextjs": [
        "200+ Cursor prompts for React/Next.js development. Components, hooks, App Router patterns. All tested. #ReactJS #Cursor #AI",
        "Next.js 14 boilerplate with Claude Code integration. Auth, DB, API pre-configured. Ship faster with AI. #NextJS #webdev",
    ],
    "devops_cloud": [
        "Updated Docker cheat sheet for 2026: CLI commands, Compose v2, multi-stage builds, security best practices. #Docker #DevOps",
        "AWS + Terraform patterns I use daily: VPC, ECS, RDS modules, CI/CD with GitHub Actions. Battle-tested. #AWS #Terraform",
    ],
    "mobile_dev": [
        "React Native AI starter: Expo + TypeScript + Claude API integration. Chat UI, voice input, 50+ prompts. #ReactNative #AI",
        "Flutter toolkit for AI features: chat widgets, streaming responses, offline caching. Works with GPT-4/Claude. #Flutter #AI",
    ],
}

_SIMULATION_TWEETS_GENERIC = [
    "New dataset released: cleaned and ready for ML projects. Normalized, deduplicated, UTF-8. #DataScience #MachineLearning",
]

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a developer and data science expert participating authentically in Reddit communities.
Generate a single Reddit post that is genuinely helpful, educational, and non-promotional.
The post should:
- Provide real value to the community
- Match the specific product type and audience provided
- Mention the store link naturally at the end
- Never read as spam or a sales pitch
- Match the tone and norms of the target subreddit
- Be written in English

Respond ONLY with a valid JSON object with these keys:
- "title": post title (string, max 300 chars)
- "body": post body in Markdown (string)
- "subreddit": the subreddit (string, without 'r/')
- "score_estimado": estimated upvote score 1-100 (integer)
- "style": the post style used (string)

No markdown fences, no explanation — just the JSON object.
"""

_TWEET_SYSTEM_PROMPT = """\
You are a developer communicating on Twitter/X.
Generate a single tweet (STRICTLY ≤ 280 characters including spaces and hashtags) that:
- Delivers one concrete insight about the product
- Feels native to Twitter — punchy, direct, technical
- Ends with 2-3 relevant hashtags
- Optionally includes the URL if it fits naturally

Respond ONLY with the raw tweet text — no quotes, no explanation, no markdown.
"""


# ---------------------------------------------------------------------------
# Content Agents
# ---------------------------------------------------------------------------

class TwitterContentAgent:
    """Generate tweet text from a Reddit post via Claude API (or simulation)."""

    def __init__(self) -> None:
        self.api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self._simulation: bool = not bool(self.api_key)
        self._sim_index: int = 0
        if self._simulation:
            logger.info("[TwitterContentAgent] Running in simulation mode (no API key).")

    def generate_tweet(
        self,
        post: dict,
        store_url: str | None = None,
        farm_type: str | None = None,
    ) -> str:
        """Generate a tweet (≤280 chars) based on *post*.

        Returns the raw tweet text string.
        """
        if self._simulation:
            return self._sim_tweet(post, farm_type)
        return self._api_tweet(post, store_url, farm_type)

    def _api_tweet(self, post: dict, store_url: str | None, farm_type: str | None) -> str:
        import anthropic

        config = FARM_CONFIG.get(farm_type, {})
        product_type = config.get("product_type", "digital product")
        audience = config.get("audience", "developers")

        url_hint = f"\nStore URL (include if it fits): {store_url}" if store_url else ""
        prompt = (
            f"Reddit post title: {post.get('title', '')}\n"
            f"Product type: {product_type}\n"
            f"Target audience: {audience}\n"
            f"Subreddit: r/{post.get('subreddit', '')}{url_hint}\n\n"
            "Write one tweet (≤280 chars) promoting this product."
        )

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                system=_TWEET_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if len(text) > 280:
                text = text[:277] + "..."
            logger.info("[TwitterContentAgent] Tweet (%d chars) generated.", len(text))
            return text
        except Exception as exc:
            logger.warning(
                "[TwitterContentAgent] API error (%s) — falling back to simulation.", exc
            )
            return self._sim_tweet(post, farm_type)

    def _sim_tweet(self, post: dict, farm_type: str | None) -> str:
        tweets = _SIMULATION_TWEETS_BY_FARM.get(farm_type, _SIMULATION_TWEETS_GENERIC)
        idx = self._sim_index % len(tweets)
        self._sim_index += 1
        return tweets[idx]


class RedditContentAgent:
    """Generate organic Reddit posts via Claude API (or simulation)."""

    def __init__(self) -> None:
        self.api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self._simulation: bool = not bool(self.api_key)
        self._style_index: int = 0
        self._sim_indices: dict[str, int] = {}  # Track per-farm simulation index
        if self._simulation:
            logger.info("[RedditContentAgent] Running in simulation mode (no API key).")

    def _next_style(self) -> str:
        style = _STYLES[self._style_index % len(_STYLES)]
        self._style_index += 1
        return style

    def generate_post(
        self,
        subreddit: str,
        product_type: str = "cleaned_dataset",
        store_url: str | None = None,
        farm_type: str | None = None,
    ) -> dict:
        """Generate a Reddit post dict for a specific farm.

        Returns keys: title, body, subreddit, score_estimado, style.
        """
        style = self._next_style()
        if self._simulation:
            return self._sim_post(subreddit, style, farm_type)
        return self._api_post(subreddit, product_type, store_url, style, farm_type)

    def _api_post(
        self,
        subreddit: str,
        product_type: str,
        store_url: str | None,
        style: str,
        farm_type: str | None,
    ) -> dict:
        import anthropic

        config = FARM_CONFIG.get(farm_type, {})
        niches = config.get("niches", [])
        audience = config.get("audience", "developers")
        actual_product_type = config.get("product_type", product_type)

        niche_hint = f"\nNiche focus: {random.choice(niches)}" if niches else ""
        url_hint = f"\nStore URL (mention at end): {store_url}" if store_url else ""

        prompt = (
            f"Target subreddit: r/{subreddit}\n"
            f"Product type: {actual_product_type}\n"
            f"Target audience: {audience}{niche_hint}\n"
            f"Post style: {style}{url_hint}\n\n"
            "Generate a Reddit post. Return JSON with: title, body, subreddit, score_estimado, style."
        )

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1].lstrip("json").strip() if len(parts) > 1 else text

            post = json.loads(text)
            post.setdefault("subreddit", subreddit)
            post.setdefault("style", style)
            post.setdefault("score_estimado", 50)
            logger.info(
                "[RedditContentAgent] Post generated for r/%s (farm=%s) — score=%s",
                subreddit, farm_type, post.get("score_estimado"),
            )
            return post

        except Exception as exc:
            logger.warning(
                "[RedditContentAgent] API error (%s) — falling back to simulation.", exc
            )
            return self._sim_post(subreddit, style, farm_type)

    def _sim_post(self, subreddit: str, style: str, farm_type: str | None) -> dict:
        posts = _SIMULATION_POSTS_BY_FARM.get(farm_type, _SIMULATION_POSTS_GENERIC)

        # Get next post for this farm (rotate through available posts)
        idx = self._sim_indices.get(farm_type, 0)
        post = dict(posts[idx % len(posts)])
        self._sim_indices[farm_type] = idx + 1

        post["subreddit"] = subreddit
        return post
