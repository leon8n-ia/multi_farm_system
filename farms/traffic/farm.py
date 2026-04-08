"""TrafficFarm: generates organic Reddit posts + tweets per farm type,
exports everything to traffic_queue.md in the project root.

Rotates through active farms, generating farm-specific content with
appropriate subreddits, product descriptions, and Gumroad links.
"""
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from farms.base_farm import BaseFarm
from farms.seller_agent import SellerAgent
from farms.traffic.content_agent import FARM_CONFIG, RedditContentAgent, TwitterContentAgent
from farms.traffic.discord_bridge import DiscordBridge
from farms.traffic.twitter_bridge import TwitterBridge
from shared.models import FarmType

logger = logging.getLogger(__name__)

TRAFFIC_QUEUE_PATH = Path("traffic_queue.md")
TRAFFIC_ARCHIVE_PATH = Path("traffic_archive.md")
MIN_PENDING_POSTS = 4
MAX_PENDING_POSTS = 8

# All productive farms that can generate traffic
PRODUCTIVE_FARMS = [
    "data_cleaning",
    "auto_reports",
    "product_listing",
    "monetized_content",
    "react_nextjs",
    "devops_cloud",
    "mobile_dev",
]

_SELLER_STRATEGY: dict = {
    "primary_channel": "reddit",
    "pricing_model": "free",
    "base_price": 0.0,
    "discount_threshold": 0,
    "discount_rate": 0.0,
    "listing_quality": "high",
    "target_audience": "developers",
    "bundle_strategy": False,
}


class TrafficFarm(BaseFarm):
    """Generates Reddit posts + tweets rotating through all productive farms."""

    def __init__(
        self,
        id: str,
        name: str,
        capital: float,
        credits: float,
        store_url: str | None = None,
    ) -> None:
        super().__init__(id, name, FarmType.MIXED, capital, credits)
        self.store_url = store_url
        self.content_agent = RedditContentAgent()
        self.twitter_content_agent = TwitterContentAgent()
        self.twitter_bridge = TwitterBridge()
        self.discord_bridge = DiscordBridge()
        self.seller_agent = SellerAgent(farm_id=id, strategy=dict(_SELLER_STRATEGY))
        self.product_type = "reddit_post"
        self._farm_index: int = 0
        self._posts_generated: int = 0
        logger.info("[%s] Discord: simulation_mode=%s", name, self.discord_bridge._simulation)

    def _next_farm(self) -> str:
        """Rotate through productive farms."""
        farm = PRODUCTIVE_FARMS[self._farm_index % len(PRODUCTIVE_FARMS)]
        self._farm_index += 1
        return farm

    def _get_farm_config(self, farm_type: str) -> dict:
        """Get configuration for a farm type."""
        return FARM_CONFIG.get(farm_type, {})

    def _get_subreddit_for_farm(self, farm_type: str) -> str:
        """Get appropriate subreddit for a farm type."""
        config = self._get_farm_config(farm_type)
        subreddits = config.get("subreddits", ["datascience"])
        # Alternate between available subreddits
        idx = self._posts_generated % len(subreddits)
        return subreddits[idx]

    def _get_gumroad_url_for_farm(self, farm_type: str) -> str:
        """Get Gumroad URL for a farm type."""
        farm_config = self._get_farm_config(farm_type)
        return farm_config.get("gumroad_url", self.store_url or "")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run_cycle(self) -> None:
        self.run_production()
        self.run_competition()
        self.run_sales()
        self.apply_economics()
        self.eliminate_dead()
        self.reproduce_winners()
        self.calculate_performance()
        self.cycles_alive += 1

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def run_production(self) -> None:
        """Generate one Reddit post + one tweet for the next farm in rotation.

        Manages queue size: archives published posts and skips generation
        if pending posts >= MAX_PENDING_POSTS (8).
        """
        # 0 — Archive any published posts first
        self._archive_published_posts()

        # 0.1 — Check pending count, skip if at max
        pending_count = self._count_pending_posts()
        if pending_count >= MAX_PENDING_POSTS:
            logger.info(
                "[%s] Queue has %d pending posts (max %d), skipping generation",
                self.name, pending_count, MAX_PENDING_POSTS,
            )
            return

        # Get next farm in rotation
        farm_type = self._next_farm()
        subreddit = self._get_subreddit_for_farm(farm_type)
        gumroad_url = self._get_gumroad_url_for_farm(farm_type)
        farm_config = self._get_farm_config(farm_type)
        product_type = farm_config.get("product_type", "digital product")

        # 1 — Reddit post
        post = self.content_agent.generate_post(
            subreddit=subreddit,
            product_type=product_type,
            store_url=gumroad_url,
            farm_type=farm_type,
        )
        post["timestamp"] = datetime.now().isoformat(timespec="seconds")
        post["niche"] = farm_type
        post["farm_type"] = farm_type
        post["gumroad_url"] = gumroad_url
        post["product_type"] = product_type

        # 2 — Tweet derived from the Reddit post
        tweet_text = self.twitter_content_agent.generate_tweet(
            post=post,
            store_url=gumroad_url,
            farm_type=farm_type,
        )
        tweet_result = self.twitter_bridge.post_tweet(tweet_text)
        post["tweet"] = {
            "text": tweet_text,
            **tweet_result,
        }

        # 3 — Discord posts (secondary channel)
        discord_results: list[dict] = []
        if config.DISCORD_ENABLED and config.DISCORD_TARGET_CHANNELS:
            discord_msg = self.discord_bridge.format_post(
                product=post.get("title", "New Product"),
                niche=farm_type,
                platform_url=gumroad_url,
            )
            for ch_id in config.DISCORD_TARGET_CHANNELS:
                try:
                    ok = self.discord_bridge.post_content(discord_msg, str(ch_id))
                except Exception as exc:
                    logger.warning("[%s] Discord channel %s error: %s", self.name, ch_id, exc)
                    ok = False
                discord_results.append({"channel_id": str(ch_id), "ok": ok, "niche": farm_type})
        post["discord"] = discord_results

        self.output_buffer.append(post)
        self._posts_generated += 1

        sim_tag = " [sim]" if tweet_result["simulation"] else ""
        logger.info(
            "[%s] Post generated — farm=%s | r/%s | %s%s",
            self.name,
            farm_type,
            post.get("subreddit"),
            product_type,
            sim_tag,
        )

    def run_competition(self) -> Any:
        """No competition — returns the latest buffered post."""
        return self.output_buffer[-1] if self.output_buffer else None

    def run_sales(self) -> None:
        """Export buffered posts to traffic_queue.md and record history entries."""
        if not self.output_buffer:
            return

        self._export_to_queue(self.output_buffer)

        for post in self.output_buffer:
            tweet = post.get("tweet", {})
            self.seller_agent.sales_history.append({
                "sold": True,
                "price": 0.0,
                "item": f"r/{post.get('subreddit', '?')} post",
                "subreddit": post.get("subreddit"),
                "farm_type": post.get("farm_type"),
                "style": post.get("style"),
                "tweet_url": tweet.get("url"),
                "tweet_simulation": tweet.get("simulation", True),
                "discord_channels": post.get("discord", []),
            })

        self.output_buffer.clear()

    def apply_economics(self) -> None:
        pass

    def eliminate_dead(self) -> None:
        pass

    def reproduce_winners(self) -> None:
        pass

    def calculate_performance(self) -> None:
        self.roi = 0.0

    # ------------------------------------------------------------------
    # Queue Management
    # ------------------------------------------------------------------

    def _parse_queue_posts(self) -> list[dict]:
        """Parse all posts from traffic_queue.md with their status."""
        if not TRAFFIC_QUEUE_PATH.exists():
            return []
        try:
            content = TRAFFIC_QUEUE_PATH.read_text(encoding="utf-8")
        except OSError:
            return []

        posts: list[dict] = []
        header_pattern = re.compile(
            r"^## \[(.+?)\] r/(\w+) — (.+?) \| (.+?) \| Status: (\w+)$"
        )
        title_pattern = re.compile(r"^\*\*Título:\*\* (.+)$")

        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            header_match = header_pattern.match(line)
            if header_match:
                timestamp, subreddit, style, niche, status = header_match.groups()

                block_lines = [line]
                title = ""
                i += 1
                while i < len(lines) and not lines[i].startswith("---"):
                    block_lines.append(lines[i])
                    title_match = title_pattern.match(lines[i])
                    if title_match:
                        title = title_match.group(1).strip()
                    i += 1
                if i < len(lines) and lines[i].startswith("---"):
                    block_lines.append(lines[i])
                    i += 1

                posts.append({
                    "timestamp": timestamp,
                    "subreddit": subreddit,
                    "style": style,
                    "niche": niche,
                    "status": status,
                    "title": title,
                    "raw_block": "\n".join(block_lines),
                })
            else:
                i += 1

        return posts

    def _archive_published_posts(self) -> int:
        """Move posts with status=published to traffic_archive.md."""
        posts = self._parse_queue_posts()
        published = [p for p in posts if p["status"] == "published"]
        pending = [p for p in posts if p["status"] == "pending"]

        if not published:
            return 0

        archive_content = "\n\n".join(p["raw_block"] for p in published) + "\n\n"
        try:
            if not TRAFFIC_ARCHIVE_PATH.exists():
                TRAFFIC_ARCHIVE_PATH.write_text(
                    "# Traffic Archive — Published Posts\n\n"
                    "_Archived by TrafficFarm after publication._\n\n",
                    encoding="utf-8",
                )
            with TRAFFIC_ARCHIVE_PATH.open("a", encoding="utf-8") as f:
                f.write(archive_content)
        except OSError as exc:
            logger.error("[%s] Failed to write archive: %s", self.name, exc)
            return 0

        try:
            queue_header = (
                "# Traffic Queue — Reddit Posts & Tweets\n\n"
                "_Generated by TrafficFarm. Copy-paste to Reddit / Twitter._\n\n"
            )
            pending_content = "\n\n".join(p["raw_block"] for p in pending)
            if pending_content:
                pending_content += "\n\n"
            TRAFFIC_QUEUE_PATH.write_text(queue_header + pending_content, encoding="utf-8")
        except OSError as exc:
            logger.error("[%s] Failed to rewrite queue: %s", self.name, exc)
            return 0

        logger.info(
            "[%s] Archived %d published post(s), %d pending remain",
            self.name, len(published), len(pending),
        )
        return len(published)

    def _count_pending_posts(self) -> int:
        """Count posts with status=pending in the queue."""
        posts = self._parse_queue_posts()
        return len([p for p in posts if p["status"] == "pending"])

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _get_existing_post_hashes(self) -> set[str]:
        """Extract hashes of existing posts from traffic_queue.md."""
        if not TRAFFIC_QUEUE_PATH.exists():
            return set()
        try:
            content = TRAFFIC_QUEUE_PATH.read_text(encoding="utf-8")
        except OSError:
            return set()

        hashes: set[str] = set()
        header_pattern = re.compile(r"^## \[.*?\] r/(\w+) —")
        title_pattern = re.compile(r"^\*\*Título:\*\* (.+)$")

        current_subreddit: str | None = None
        for line in content.splitlines():
            header_match = header_pattern.match(line)
            if header_match:
                current_subreddit = header_match.group(1)
                continue
            title_match = title_pattern.match(line)
            if title_match and current_subreddit:
                title = title_match.group(1).strip()
                key = f"{current_subreddit}|{title}"
                hashes.add(hashlib.md5(key.encode()).hexdigest())
                current_subreddit = None
        return hashes

    def _export_to_queue(self, posts: list[dict]) -> None:
        """Append posts to traffic_queue.md in copy-paste-ready Markdown."""
        existing_hashes = self._get_existing_post_hashes()
        lines: list[str] = []
        skipped = 0

        for post in posts:
            title = post.get("title", "")
            sub = post.get("subreddit", "?")
            key = f"{sub}|{title}"
            post_hash = hashlib.md5(key.encode()).hexdigest()
            if post_hash in existing_hashes:
                skipped += 1
                logger.debug("[%s] Skipping duplicate post: r/%s — %s", self.name, sub, title[:50])
                continue

            ts = post.get("timestamp", datetime.now().isoformat(timespec="seconds"))
            style = post.get("style", "?")
            farm_type = post.get("farm_type", post.get("niche", "?"))
            gumroad_url = post.get("gumroad_url", "")
            body = post.get("body", "")
            score = post.get("score_estimado", "?")
            product_type = post.get("product_type", "")
            tweet = post.get("tweet", {})
            tweet_text = tweet.get("text", "")
            tweet_url = tweet.get("url", "")
            tweet_sim = tweet.get("simulation", True)

            # --- Reddit section ---
            lines.append(f"## [{ts}] r/{sub} — {style} | {farm_type} | Status: pending")
            lines.append("")
            lines.append(f"**Farm:** {farm_type}")
            lines.append(f"**Product:** {product_type}")
            lines.append(f"**Score estimado:** {score}/100")
            lines.append("")
            lines.append(f"**Gumroad:** <{gumroad_url}>")
            lines.append("")
            lines.append(f"**Título:** {title}")
            lines.append("")
            lines.append("**Cuerpo:**")
            lines.append("")
            lines.append(body)
            lines.append("")

            # --- Tweet section ---
            sim_label = " *(simulado)*" if tweet_sim else ""
            lines.append(f"**Tweet{sim_label}:**")
            lines.append("")
            lines.append(f"> {tweet_text}")
            lines.append("")
            if tweet_url:
                lines.append(f"🐦 {tweet_url}")
                lines.append("")

            # --- Discord section ---
            discord_channels = post.get("discord", [])
            if discord_channels:
                lines.append("**Discord:**")
                lines.append("")
                for entry in discord_channels:
                    status = "OK" if entry.get("ok") else "FAILED"
                    lines.append(f"- channel `{entry['channel_id']}`: {status}")
                lines.append("")

            lines.append("---")
            lines.append("")

        if skipped:
            logger.info("[%s] Skipped %d duplicate post(s)", self.name, skipped)

        if not lines:
            return

        content = "\n".join(lines)

        try:
            if not TRAFFIC_QUEUE_PATH.exists():
                TRAFFIC_QUEUE_PATH.write_text(
                    "# Traffic Queue — Reddit Posts & Tweets\n\n"
                    "_Generated by TrafficFarm. Copy-paste to Reddit / Twitter._\n\n",
                    encoding="utf-8",
                )
            with TRAFFIC_QUEUE_PATH.open("a", encoding="utf-8") as f:
                f.write(content)
            new_count = len(posts) - skipped
            logger.info(
                "[%s] Exported %d new post(s) to %s",
                self.name, new_count, TRAFFIC_QUEUE_PATH,
            )
        except OSError as exc:
            logger.error("[%s] Failed to write %s: %s", self.name, TRAFFIC_QUEUE_PATH, exc)
