"""Thin wrapper around the Discord API for posting messages to channels.

Runs in **simulation mode** (no network calls) when DISCORD_BOT_TOKEN is absent
or discord.py is not installed.

REST API methods (post_message, get_available_channels, format_post) use
``requests`` directly — no discord.py dependency.
"""
import asyncio
import logging
import os
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

_DISCORD_CHAR_LIMIT = 2000
_DISCORD_API_BASE = "https://discord.com/api/v10"
_RATE_LIMIT_SECONDS = 60   # 1 post per minute per channel
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0         # seconds between retry attempts


async def _async_send(token: str, channel_id: int, content: str) -> bool:
    """Open a short-lived Discord client, send *content*, then close."""
    try:
        import discord
    except ImportError:
        return False

    sent = False
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready() -> None:
        nonlocal sent
        try:
            channel = client.get_channel(channel_id)
            if channel is None:
                channel = await client.fetch_channel(channel_id)
            await channel.send(content)
            sent = True
        except Exception as exc:
            logger.warning("[DiscordBridge] send to channel %s failed: %s", channel_id, exc)
        finally:
            await client.close()

    try:
        await client.start(token, reconnect=False)
    except Exception as exc:
        logger.warning("[DiscordBridge] client.start() error: %s", exc)

    return sent


class DiscordBridge:
    """Post messages to Discord channels via a bot token.

    Falls back to simulation when DISCORD_BOT_TOKEN is absent,
    discord.py is not installed, or any API call fails.
    """

    def __init__(self) -> None:
        self.token: str | None = os.environ.get("DISCORD_BOT_TOKEN")
        self._simulation: bool = not bool(self.token)
        self._rate_limit_tracker: dict[str, float] = {}

        if self._simulation:
            logger.info("Discord: simulation_mode=True (DISCORD_BOT_TOKEN not set)")
        else:
            try:
                import discord  # noqa: F401 — verify library is available at init time
                logger.info("Discord: simulation_mode=False — bot token present")
            except ImportError:
                logger.error("[DiscordBridge] discord.py not installed — falling back to simulation.")
                self._simulation = True
                logger.info("Discord: simulation_mode=True (discord.py not installed)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_content(self, content: str, channel_id: str) -> bool:
        """Post *content* to the given Discord *channel_id*.

        Truncates to 2000 characters (Discord limit) if needed.
        Returns True on success (real or simulated), False on error.
        """
        if len(content) > _DISCORD_CHAR_LIMIT:
            content = content[: _DISCORD_CHAR_LIMIT - 3] + "..."

        if self._simulation:
            return self._sim_post(content, channel_id)

        try:
            loop = asyncio.new_event_loop()
            try:
                ok = loop.run_until_complete(
                    _async_send(self.token, int(channel_id), content)
                )
            finally:
                loop.close()
            logger.info(
                "[DiscordBridge] post_content → channel %s [%s]",
                channel_id,
                "ok" if ok else "failed",
            )
            return ok
        except Exception as exc:
            logger.warning("[DiscordBridge] post_content error (%s) — returning False", exc)
            return False

    def post_message(self, channel_id: str, message: str) -> bool:
        """Post *message* to *channel_id* via Discord REST API.

        Enforces a rate limit of 1 post per minute per channel.
        Retries up to ``_MAX_RETRIES`` times on transient errors or HTTP 429.
        Returns True on success, False otherwise.
        """
        if len(message) > _DISCORD_CHAR_LIMIT:
            message = message[: _DISCORD_CHAR_LIMIT - 3] + "..."

        if self._simulation:
            return self._sim_post(message, channel_id)

        # Rate limit: enforce 1 post per minute per channel
        now = time.time()
        last = self._rate_limit_tracker.get(channel_id, 0.0)
        if now - last < _RATE_LIMIT_SECONDS:
            remaining = _RATE_LIMIT_SECONDS - (now - last)
            logger.info(
                "[DiscordBridge] rate limit: channel %s, wait %.0fs", channel_id, remaining
            )
            return False

        url = f"{_DISCORD_API_BASE}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json={"content": message}, timeout=10)
                if resp.status_code in (200, 201):
                    self._rate_limit_tracker[channel_id] = time.time()
                    logger.info(
                        "[DiscordBridge] post_message → channel %s ok (attempt %d)",
                        channel_id, attempt,
                    )
                    return True
                elif resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", _RETRY_DELAY)
                    logger.warning(
                        "[DiscordBridge] 429 rate limited by Discord, retry in %.1fs", retry_after
                    )
                    if attempt < _MAX_RETRIES:
                        time.sleep(retry_after)
                else:
                    logger.warning(
                        "[DiscordBridge] post_message → channel %s status %d (attempt %d)",
                        channel_id, resp.status_code, attempt,
                    )
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_DELAY)
            except Exception as exc:
                logger.warning("[DiscordBridge] post_message error (attempt %d): %s", attempt, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)

        return False

    def get_available_channels(self) -> list[dict]:
        """Return text channels where the bot has access.

        Fetches all guilds the bot is in, then lists text channels (type=0)
        for each guild. Returns an empty list in simulation mode or on error.
        """
        if self._simulation:
            logger.info("[DiscordBridge] [SIM] get_available_channels → []")
            return []

        headers = {"Authorization": f"Bot {self.token}"}
        channels: list[dict] = []

        try:
            guild_resp = requests.get(
                f"{_DISCORD_API_BASE}/users/@me/guilds", headers=headers, timeout=10
            )
            if guild_resp.status_code != 200:
                logger.warning(
                    "[DiscordBridge] get guilds failed: %d", guild_resp.status_code
                )
                return []

            for guild in guild_resp.json():
                guild_id = guild["id"]
                ch_resp = requests.get(
                    f"{_DISCORD_API_BASE}/guilds/{guild_id}/channels",
                    headers=headers,
                    timeout=10,
                )
                if ch_resp.status_code != 200:
                    logger.warning(
                        "[DiscordBridge] get channels for guild %s failed: %d",
                        guild_id, ch_resp.status_code,
                    )
                    continue
                for ch in ch_resp.json():
                    if ch.get("type") == 0:  # GUILD_TEXT only
                        channels.append({
                            "id": ch["id"],
                            "name": ch["name"],
                            "guild_id": guild_id,
                            "guild_name": guild.get("name", ""),
                        })
        except Exception as exc:
            logger.warning("[DiscordBridge] get_available_channels error: %s", exc)

        return channels

    def format_post(self, product: str, niche: str, platform_url: str) -> str:
        """Return organic Discord message that sounds like a dev sharing something useful."""
        templates = self._get_niche_templates(niche, platform_url)
        idx = int(time.time()) % len(templates)
        return templates[idx]

    def _get_niche_templates(self, niche: str, url: str) -> list[str]:
        """Return 3 organic templates per niche."""
        templates: dict[str, list[str]] = {
            "data_cleaning": [
                (
                    "Been working on a data cleaning pipeline for a client project. "
                    "As a byproduct I ended up with a bunch of cleaned datasets — "
                    "e-commerce, financial, sensor data.\n\n"
                    "Figured someone might find them useful for testing ML pipelines "
                    "or benchmarking. Nulls handled, outliers flagged, dtypes fixed.\n\n"
                    f"<{url}>"
                ),
                (
                    "Finally automated most of my data cleaning workflow. "
                    "The tedious part was handling mixed date formats and currency symbols "
                    "embedded in numeric fields.\n\n"
                    "Packaged a few production-ready datasets if anyone needs clean data "
                    "to prototype with instead of spending hours on preprocessing.\n\n"
                    f"<{url}>"
                ),
                (
                    "Spent way too long cleaning messy CSVs this month. "
                    "Inconsistent nulls (`N/A`, `-`, `null`, empty strings) are the worst.\n\n"
                    "If you need already-cleaned datasets for ML experiments — "
                    "saved some here so you can skip the preprocessing hell:\n\n"
                    f"<{url}>"
                ),
            ],
            "auto_reports": [
                (
                    "Built an automated reporting system for internal dashboards. "
                    "The templates are pretty flexible — PDF, Markdown, or HTML output.\n\n"
                    "Works well for weekly KPIs, quarterly summaries, or any recurring report "
                    "you're tired of generating manually.\n\n"
                    f"<{url}>"
                ),
                (
                    "Automated our team's monthly reporting workflow. "
                    "Connects to SQL/Postgres, pulls metrics, generates charts, "
                    "exports to PDF with proper formatting.\n\n"
                    "Sharing the templates in case anyone else is stuck doing this manually:\n\n"
                    f"<{url}>"
                ),
                (
                    "Our PM kept asking for the same reports every week. "
                    "Finally wrote a script that auto-generates them from the database.\n\n"
                    "If you need automated report generation with charts and tables, "
                    "I packaged the templates here:\n\n"
                    f"<{url}>"
                ),
            ],
            "product_listing": [
                (
                    "Working on an e-commerce project and needed to optimize product listings. "
                    "Ended up building a system that generates SEO-friendly descriptions "
                    "from raw product data.\n\n"
                    "Handles categorization, keyword extraction, and structured output. "
                    "Might be useful if you're dealing with large catalogs:\n\n"
                    f"<{url}>"
                ),
                (
                    "Had to migrate 5k+ product listings between platforms. "
                    "Built some tooling to normalize titles, descriptions, and attributes.\n\n"
                    "If anyone's dealing with messy product catalogs or needs to bulk-generate "
                    "listings, this might save you some time:\n\n"
                    f"<{url}>"
                ),
                (
                    "E-commerce product data is always a mess — inconsistent titles, "
                    "missing attributes, duplicate SKUs.\n\n"
                    "Wrote a pipeline that cleans and standardizes product listings. "
                    "Sharing it here if anyone needs it:\n\n"
                    f"<{url}>"
                ),
            ],
            "monetized_content": [
                (
                    "Been experimenting with content automation for technical blogs. "
                    "The key was getting the tone right — informative, not salesy.\n\n"
                    "Generates long-form content with proper code examples and formatting. "
                    "Useful for dev blogs or documentation:\n\n"
                    f"<{url}>"
                ),
                (
                    "Our content team was bottlenecked on technical writing. "
                    "Built a system that drafts articles from outlines — "
                    "handles code snippets, diagrams, and SEO.\n\n"
                    "Sharing the templates if anyone needs to scale technical content:\n\n"
                    f"<{url}>"
                ),
                (
                    "Writing technical tutorials is time-consuming. "
                    "Automated the first draft generation — still needs human review, "
                    "but saves ~70% of the initial writing time.\n\n"
                    "Templates and examples here:\n\n"
                    f"<{url}>"
                ),
            ],
            "react_nextjs": [
                (
                    "Compiled 200+ Cursor prompts for React/Next.js development. "
                    "Components, hooks, App Router patterns — all tested on real projects.\n\n"
                    "Saves a ton of time when building with AI assistance:\n\n"
                    f"<{url}>"
                ),
                (
                    "Built a Next.js 14 starter optimized for AI-assisted development. "
                    "App Router, TypeScript, shadcn/ui, plus 100+ prompts for common tasks.\n\n"
                    "Ship faster with AI:\n\n"
                    f"<{url}>"
                ),
                (
                    "If you're using Cursor or Claude for React development, "
                    "I put together a collection of prompts that work well for components, "
                    "hooks, and Next.js patterns.\n\n"
                    "Might save you some prompt engineering time:\n\n"
                    f"<{url}>"
                ),
            ],
            "devops_cloud": [
                (
                    "Updated my Docker cheat sheet for 2026 — CLI commands, Compose v2, "
                    "multi-stage builds, security best practices.\n\n"
                    "PDF + Markdown versions. Useful for quick reference:\n\n"
                    f"<{url}>"
                ),
                (
                    "Compiled AWS + Terraform patterns I use daily: VPC, ECS, RDS modules, "
                    "IAM templates, CI/CD with GitHub Actions.\n\n"
                    "Battle-tested configs if anyone needs them:\n\n"
                    f"<{url}>"
                ),
                (
                    "K8s reference I keep open daily — kubectl commands, Helm patterns, "
                    "debugging tips, RBAC quick reference.\n\n"
                    "Print-friendly PDF:\n\n"
                    f"<{url}>"
                ),
            ],
            "mobile_dev": [
                (
                    "Built a React Native starter for AI-powered apps — Expo SDK 52, "
                    "TypeScript, Claude API integration, chat UI components.\n\n"
                    "Ship mobile AI apps faster:\n\n"
                    f"<{url}>"
                ),
                (
                    "Flutter toolkit for adding AI features — pre-built chat widgets, "
                    "streaming responses, offline caching patterns.\n\n"
                    "Works with GPT-4 and Claude:\n\n"
                    f"<{url}>"
                ),
                (
                    "If you're building mobile apps with AI features, "
                    "I put together some starter code and prompts for React Native and Flutter.\n\n"
                    "Might save you some setup time:\n\n"
                    f"<{url}>"
                ),
            ],
        }
        return templates.get(niche, [
            f"Sharing a useful resource for {niche.replace('_', ' ')} workflows:\n\n<{url}>"
        ])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sim_post(self, content: str, channel_id: str) -> bool:
        fake_id = str(int(datetime.now().timestamp() * 1000))
        logger.info(
            "[DiscordBridge] [SIM] channel=%s msg_id=%s len=%d",
            channel_id,
            fake_id,
            len(content),
        )
        return True
