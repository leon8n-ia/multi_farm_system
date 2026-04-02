"""Reddit content agent: uses Claude API (Opus 4.6, adaptive thinking) to generate
organic Reddit posts promoting data products.

Falls back to simulation when ANTHROPIC_API_KEY is absent or the API call fails.
"""
import json
import logging
import os
import random

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "datasets",
    "datascience",
    "MachineLearning",
    "learnmachinelearning",
]

_STYLES = [
    "recurso gratuito",
    "tip técnico",
    "showcase de dataset",
    "pregunta con respuesta",
]

_SYSTEM_PROMPT = """\
You are a data science expert participating authentically in Reddit communities.
Generate a single Reddit post that is genuinely helpful, educational, and non-promotional.
The post should:
- Provide real value to the community
- Mention the store link naturally and briefly at the end (if provided)
- Never read as spam or a sales pitch
- Match the tone and norms of the target subreddit
- Be written in English

Respond ONLY with a valid JSON object with these keys:
- "title": post title (string, max 300 chars)
- "body": post body in Markdown (string)
- "subreddit": the chosen subreddit (string, without 'r/')
- "score_estimado": estimated upvote score 1-100 (integer)
- "style": the post style used (string)

No markdown fences, no explanation — just the JSON object.
"""

_SIMULATION_POSTS = [
    # --- recurso gratuito (3 variaciones) ---
    {
        "title": "[Resource] Free cleaned e-commerce dataset — 10k product records, ready to use",
        "body": (
            "Hi r/datascience! I've been working on a data cleaning pipeline and as a "
            "byproduct I have a cleaned e-commerce dataset (10,000 product records) with:\n\n"
            "- Normalized category labels\n"
            "- Price outliers removed (>3σ)\n"
            "- Duplicate records deduplicated\n"
            "- UTF-8 encoded, no BOM\n\n"
            "Good baseline for recommendation systems or price-prediction models. "
            "Download it free at [Multi Farm System](https://multifarm.lemonsqueezy.com).\n\n"
            "Happy to answer questions about the cleaning methodology!"
        ),
        "subreddit": "datascience",
        "score_estimado": 85,
        "style": "recurso gratuito",
    },
    {
        "title": "[Free Dataset] 5000 annotated product reviews for sentiment analysis",
        "body": (
            "Sharing a dataset I curated for a sentiment analysis project:\n\n"
            "**5,000 product reviews** with:\n"
            "- Manual sentiment labels (positive/negative/neutral)\n"
            "- Star ratings (1-5)\n"
            "- Product categories\n"
            "- Cleaned text (no HTML, normalized unicode)\n\n"
            "Great for training classifiers or benchmarking NLP models. "
            "Grab it at [Multi Farm System](https://multifarm.lemonsqueezy.com).\n\n"
            "Let me know if you'd like the labeling guidelines I used!"
        ),
        "subreddit": "datascience",
        "score_estimado": 78,
        "style": "recurso gratuito",
    },
    {
        "title": "Releasing a free dataset: 20k daily stock prices with technical indicators",
        "body": (
            "For anyone working on financial ML projects, I'm releasing a dataset with:\n\n"
            "- 20,000 daily records across 50 tickers\n"
            "- OHLCV data + pre-calculated indicators (RSI, MACD, Bollinger Bands)\n"
            "- Adjusted for splits and dividends\n"
            "- No missing values or weekends\n\n"
            "Useful for backtesting strategies or training price prediction models. "
            "Download: [Multi Farm System](https://multifarm.lemonsqueezy.com)"
        ),
        "subreddit": "datasets",
        "score_estimado": 82,
        "style": "recurso gratuito",
    },

    # --- tip técnico (3 variaciones) ---
    {
        "title": "I cleaned 50k rows of messy financial data — here's what I learned",
        "body": (
            "Working with real-world financial datasets is humbling. After spending weeks "
            "cleaning 50k+ rows, here are the most common issues:\n\n"
            "1. **Mixed date formats** — some rows had ISO 8601, others MM/DD/YY\n"
            "2. **Currency symbols embedded in numeric fields** — `$1,234.56` vs `1234.56`\n"
            "3. **Inconsistent null representations** — `'N/A'`, `'null'`, `'-'`, `''`, `0`\n\n"
            "The tool that saved me the most time: a regex-based type-inference pass before "
            "loading into pandas. Happy to share the script.\n\n"
            "If you need pre-cleaned datasets to validate your pipelines, "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com) has a few available."
        ),
        "subreddit": "datasets",
        "score_estimado": 72,
        "style": "tip técnico",
    },
    {
        "title": "The one pandas trick that cut my data cleaning time in half",
        "body": (
            "After years of data wrangling, this pattern has saved me countless hours:\n\n"
            "```python\n"
            "# Chain operations with pipe() for readable transformations\n"
            "df = (raw_df\n"
            "    .pipe(normalize_columns)\n"
            "    .pipe(remove_outliers, threshold=3)\n"
            "    .pipe(fill_missing, strategy='median')\n"
            "    .pipe(validate_schema))\n"
            "```\n\n"
            "Each function is testable, reusable, and the pipeline is self-documenting.\n\n"
            "More cleaning utilities and sample datasets at "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "learnmachinelearning",
        "score_estimado": 68,
        "style": "tip técnico",
    },
    {
        "title": "Stop using df.apply() for everything — here's why vectorization matters",
        "body": (
            "I see this mistake constantly in data cleaning code:\n\n"
            "```python\n"
            "# Slow: 45 seconds on 1M rows\n"
            "df['clean'] = df['text'].apply(lambda x: x.lower().strip())\n\n"
            "# Fast: 0.3 seconds on 1M rows\n"
            "df['clean'] = df['text'].str.lower().str.strip()\n"
            "```\n\n"
            "Vectorized string methods are 100x+ faster. Same applies to numeric operations.\n\n"
            "I've compiled benchmarks and optimized cleaning functions at "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "datascience",
        "score_estimado": 75,
        "style": "tip técnico",
    },

    # --- pregunta con respuesta (3 variaciones) ---
    {
        "title": "What's your go-to strategy for handling missing values in clustered time series?",
        "body": (
            "Working on a sensor dataset with ~12% missing values distributed non-randomly. "
            "Gaps tend to cluster (equipment downtime), so simple interpolation gives "
            "misleading results.\n\n"
            "I've tried:\n"
            "- Forward fill → introduces lag artifacts\n"
            "- Cubic spline → oscillates near large gaps\n"
            "- MICE imputation → slow but decent\n\n"
            "What's your preferred approach for clustered missingness in time series?\n\n"
            "For reference: [sample raw vs. cleaned data here]"
            "(https://multifarm.lemonsqueezy.com) if you want to experiment."
        ),
        "subreddit": "MachineLearning",
        "score_estimado": 61,
        "style": "pregunta con respuesta",
    },
    {
        "title": "How do you handle categorical variables with 500+ unique values?",
        "body": (
            "Working on a retail dataset where `product_id` has 500+ unique values. "
            "One-hot encoding explodes dimensionality, but label encoding loses semantics.\n\n"
            "Currently considering:\n"
            "- Target encoding (risk of leakage)\n"
            "- Embedding layers (requires deep learning)\n"
            "- Frequency encoding (loses rare categories)\n\n"
            "What's worked best for you in production?\n\n"
            "Dataset available for testing at "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "datascience",
        "score_estimado": 58,
        "style": "pregunta con respuesta",
    },
    {
        "title": "Best practices for versioning datasets in ML projects?",
        "body": (
            "My team keeps running into reproducibility issues. Training data changes, "
            "models break, and nobody knows which dataset version was used.\n\n"
            "We've tried:\n"
            "- Git LFS (slow, storage limits)\n"
            "- DVC (decent but complex setup)\n"
            "- Manual versioning with timestamps (error-prone)\n\n"
            "What's your workflow for dataset versioning?\n\n"
            "Sample versioned datasets for reference: "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "MachineLearning",
        "score_estimado": 64,
        "style": "pregunta con respuesta",
    },

    # --- showcase de dataset (3 variaciones) ---
    {
        "title": "Showcase: automated data-quality report for any CSV in under 10 seconds",
        "body": (
            "Built a small tool that generates a data-quality report for any CSV:\n\n"
            "```python\nfrom data_quality import report\nreport('my_data.csv')\n```\n\n"
            "Output includes: missing-value heatmap, type inference, duplicate detection, "
            "outlier flagging, and a cleanliness score (0–100).\n\n"
            "We use this internally before releasing cleaned datasets at "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com). "
            "Happy to open-source the report generator if there's interest!"
        ),
        "subreddit": "learnmachinelearning",
        "score_estimado": 54,
        "style": "showcase de dataset",
    },
    {
        "title": "Built a dataset of 15k job postings with salary data — sharing insights",
        "body": (
            "Scraped and cleaned 15,000 job postings from the last 6 months:\n\n"
            "**Key findings:**\n"
            "- Remote roles pay 12% more on average\n"
            "- 'Senior' in title adds ~$25k to median salary\n"
            "- Python demand up 23% YoY\n\n"
            "Dataset includes: title, company, location, salary range, skills required.\n\n"
            "Full dataset available at "
            "[Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "datascience",
        "score_estimado": 71,
        "style": "showcase de dataset",
    },
    {
        "title": "Created a benchmark dataset for testing data cleaning pipelines",
        "body": (
            "Tired of not having a standard way to test cleaning code, so I made one:\n\n"
            "**The Messy Data Benchmark** includes:\n"
            "- 10 CSV files with known issues (duplicates, nulls, outliers, encoding)\n"
            "- Ground truth 'clean' versions\n"
            "- Scoring script to measure cleaning accuracy\n\n"
            "Great for unit testing or comparing cleaning libraries.\n\n"
            "Download at [Multi Farm System](https://multifarm.lemonsqueezy.com)."
        ),
        "subreddit": "datasets",
        "score_estimado": 66,
        "style": "showcase de dataset",
    },
]


_TWEET_SYSTEM_PROMPT = """\
You are a data science communicator writing for Twitter/X.
Generate a single tweet (STRICTLY ≤ 280 characters including spaces and hashtags) that:
- Delivers one concrete insight or tip from the provided Reddit post
- Feels native to Twitter — punchy, direct, no filler
- Ends with 2-3 relevant hashtags (#DataScience #MachineLearning #datasets etc.)
- Optionally includes the store URL if it fits naturally

Respond ONLY with the raw tweet text — no quotes, no explanation, no markdown.
"""

_SIMULATION_TWEETS = [
    (
        "Cleaned 50k financial rows. Top pain points: mixed date formats, "
        "embedded currency symbols, inconsistent nulls. "
        "Fix type inference before pandas. #DataScience #DataCleaning #datasets"
    ),
    (
        "Free cleaned e-commerce dataset: 10k products, normalized labels, "
        "outliers removed, deduped. Great baseline for recommendation systems. "
        "Link in bio: multifarm.lemonsqueezy.com #MachineLearning #OpenData"
    ),
    (
        "MICE > forward-fill for clustered missing values in time series. "
        "Forward-fill introduces lag artifacts near equipment-downtime gaps. "
        "What's your go-to? #DataScience #TimeSeries"
    ),
    (
        "Built a CSV data-quality report: missing-value heatmap, type inference, "
        "duplicate detection, outlier flags, cleanliness score 0–100. "
        "Open-sourcing soon. #Python #DataEngineering"
    ),
]


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
    ) -> str:
        """Generate a tweet (≤280 chars) based on *post*.

        Returns the raw tweet text string.
        """
        if self._simulation:
            return self._sim_tweet(post)
        return self._api_tweet(post, store_url)

    def _api_tweet(self, post: dict, store_url: str | None) -> str:
        import anthropic

        url_hint = f"\nStore URL (include if it fits): {store_url}" if store_url else ""
        prompt = (
            f"Reddit post title: {post.get('title', '')}\n"
            f"Style: {post.get('style', '')}\n"
            f"Subreddit: r/{post.get('subreddit', '')}{url_hint}\n\n"
            "Write one tweet (≤280 chars) distilling the key insight."
        )

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=150,
                thinking={"type": "adaptive"},
                system=_TWEET_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = next(
                block.text for block in response.content if block.type == "text"
            ).strip()
            # Enforce hard limit
            if len(text) > 280:
                text = text[:277] + "..."
            logger.info("[TwitterContentAgent] Tweet (%d chars) generated.", len(text))
            return text
        except Exception as exc:
            logger.warning(
                "[TwitterContentAgent] API error (%s) — falling back to simulation.", exc
            )
            return self._sim_tweet(post)

    def _sim_tweet(self, post: dict) -> str:
        style = post.get("style", "")
        style_map = {s: i for i, s in enumerate(_STYLES)}
        idx = style_map.get(style, self._sim_index) % len(_SIMULATION_TWEETS)
        self._sim_index += 1
        return _SIMULATION_TWEETS[idx]


class RedditContentAgent:
    """Generate organic Reddit posts via Claude API (or simulation)."""

    def __init__(self) -> None:
        self.api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self._simulation: bool = not bool(self.api_key)
        self._style_index: int = 0
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
    ) -> dict:
        """Generate a Reddit post dict.

        Returns keys: title, body, subreddit, score_estimado, style.
        """
        style = self._next_style()
        if self._simulation:
            return self._sim_post(subreddit, style)
        return self._api_post(subreddit, product_type, store_url, style)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api_post(
        self,
        subreddit: str,
        product_type: str,
        store_url: str | None,
        style: str,
    ) -> dict:
        import anthropic

        url_hint = f"\nStore URL (mention naturally at the end): {store_url}" if store_url else ""
        prompt = (
            f"Target subreddit: r/{subreddit}\n"
            f"Product type: {product_type}\n"
            f"Post style: {style}{url_hint}\n\n"
            "Return a JSON object with keys: title, body, subreddit, score_estimado, style."
        )

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = stream.get_final_message()

            # Extract the text block (skip thinking blocks)
            text = next(
                block.text for block in response.content if block.type == "text"
            )
            text = text.strip()
            # Strip markdown fences if the model wrapped the JSON
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1].lstrip("json").strip() if len(parts) > 1 else text

            post = json.loads(text)
            post.setdefault("subreddit", subreddit)
            post.setdefault("style", style)
            post.setdefault("score_estimado", 50)
            logger.info(
                "[RedditContentAgent] Post generated for r/%s — score_est=%s",
                subreddit, post.get("score_estimado"),
            )
            return post

        except Exception as exc:
            logger.warning(
                "[RedditContentAgent] API error (%s) — falling back to simulation.", exc
            )
            return self._sim_post(subreddit, style)

    def _sim_post(self, subreddit: str, style: str) -> dict:
        matches = [p for p in _SIMULATION_POSTS if p["style"] == style]
        post = dict(random.choice(matches if matches else _SIMULATION_POSTS))
        post["subreddit"] = subreddit
        post["style"] = style
        return post
