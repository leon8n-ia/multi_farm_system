"""TrafficFarm: generates organic Reddit posts + tweets each cycle,
exports everything to traffic_queue.md in the project root.
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
from farms.traffic.content_agent import SUBREDDITS, RedditContentAgent, TwitterContentAgent
from farms.traffic.discord_bridge import DiscordBridge
from farms.traffic.twitter_bridge import TwitterBridge
from shared.models import FarmType

logger = logging.getLogger(__name__)

TRAFFIC_QUEUE_PATH = Path("traffic_queue.md")
TRAFFIC_ARCHIVE_PATH = Path("traffic_archive.md")
MIN_PENDING_POSTS = 4
MAX_PENDING_POSTS = 8

# Niches rotate each cycle, mapped to Gumroad URLs
NICHES = list(config.GUMROAD_PRODUCT_URLS.keys())

_SELLER_STRATEGY: dict = {
    "primary_channel": "reddit",
    "pricing_model": "free",
    "base_price": 0.0,
    "discount_threshold": 0,
    "discount_rate": 0.0,
    "listing_quality": "high",
    "target_audience": "data_scientists",
    "bundle_strategy": False,
}


class TrafficFarm(BaseFarm):
    """Generates one Reddit post + one tweet per cycle, queued in traffic_queue.md."""

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
        self._subreddit_index: int = 0
        self._niche_index: int = 0
        self._posts_generated: int = 0
        logger.info("[%s] Discord: simulation_mode=%s", name, self.discord_bridge._simulation)

    def _next_niche(self) -> str:
        niche = NICHES[self._niche_index % len(NICHES)]
        self._niche_index += 1
        return niche

    def _next_subreddit(self) -> str:
        sub = SUBREDDITS[self._subreddit_index % len(SUBREDDITS)]
        self._subreddit_index += 1
        return sub

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
        """Generate one Reddit post + one tweet and buffer both.

        Manages queue size: archives published posts and skips generation
        if pending posts >= MAX_PENDING_POSTS (8).
        """
        # 0 — Archive any published posts first
        archived = self._archive_published_posts()

        # 0.1 — Check pending count, skip if at max
        pending_count = self._count_pending_posts()
        if pending_count >= MAX_PENDING_POSTS:
            logger.info(
                "[%s] Queue has %d pending posts (max %d), skipping generation",
                self.name, pending_count, MAX_PENDING_POSTS,
            )
            return

        subreddit = self._next_subreddit()
        niche = self._next_niche()
        gumroad_url = config.GUMROAD_PRODUCT_URLS.get(niche, self.store_url)

        # 1 — Reddit post
        post = self.content_agent.generate_post(
            subreddit=subreddit,
            product_type=niche,
            store_url=gumroad_url,
        )
        post["timestamp"] = datetime.now().isoformat(timespec="seconds")
        post["niche"] = niche
        post["gumroad_url"] = gumroad_url

        # 2 — Tweet derived from the Reddit post
        tweet_text = self.twitter_content_agent.generate_tweet(
            post=post, store_url=gumroad_url
        )
        tweet_result = self.twitter_bridge.post_tweet(tweet_text)
        post["tweet"] = {
            "text": tweet_text,
            **tweet_result,  # tweet_id, url, simulation
        }

        # 3 — Discord posts (secondary channel, additive — failures are absorbed)
        discord_results: list[dict] = []
        if config.DISCORD_ENABLED and config.DISCORD_TARGET_CHANNELS:
            niche_label = niche.replace("_", " ").title()
            discord_msg = self.discord_bridge.format_post(
                product=post.get("title", "New Product"),
                niche=niche,
                platform_url=gumroad_url,
            )
            for ch_id in config.DISCORD_TARGET_CHANNELS:
                try:
                    ok = self.discord_bridge.post_content(discord_msg, str(ch_id))
                except Exception as exc:
                    logger.warning("[%s] Discord channel %s error: %s", self.name, ch_id, exc)
                    ok = False
                discord_results.append({"channel_id": str(ch_id), "ok": ok, "niche": niche})
        post["discord"] = discord_results

        self.output_buffer.append(post)
        sim_tag = " [sim]" if tweet_result["simulation"] else ""
        logger.info(
            "[%s] Post+tweet generated — r/%s | style=%s | tweet%s: %s",
            self.name,
            post.get("subreddit"),
            post.get("style"),
            sim_tag,
            tweet_result["url"],
        )

    def run_competition(self) -> Any:
        """No competition — returns the latest buffered post."""
        return self.output_buffer[-1] if self.output_buffer else None

    def run_sales(self) -> None:
        """Export buffered posts to traffic_queue.md and record history entries."""
        if not self.output_buffer:
            return

        self._export_to_queue(self.output_buffer)
        self._posts_generated += len(self.output_buffer)

        for post in self.output_buffer:
            tweet = post.get("tweet", {})
            self.seller_agent.sales_history.append({
                "sold": True,
                "price": 0.0,
                "item": f"r/{post.get('subreddit', '?')} post",
                "subreddit": post.get("subreddit"),
                "style": post.get("style"),
                "tweet_url": tweet.get("url"),
                "tweet_simulation": tweet.get("simulation", True),
                "discord_channels": post.get("discord", []),
            })

        self.output_buffer.clear()

    def apply_economics(self) -> None:
        pass  # No credit economy for this farm

    def eliminate_dead(self) -> None:
        pass  # No producer agents

    def reproduce_winners(self) -> None:
        pass  # No reproduction

    def calculate_performance(self) -> None:
        # roi = 0 keeps the supervisor from trying to expand this farm
        self.roi = 0.0

    # ------------------------------------------------------------------
    # Queue Management
    # ------------------------------------------------------------------

    def _parse_queue_posts(self) -> list[dict]:
        """Parse all posts from traffic_queue.md with their status.

        Returns list of dicts with: timestamp, subreddit, style, niche, status, title, raw_block
        """
        if not TRAFFIC_QUEUE_PATH.exists():
            return []
        try:
            content = TRAFFIC_QUEUE_PATH.read_text(encoding="utf-8")
        except OSError:
            return []

        posts: list[dict] = []
        # New format: ## [timestamp] r/subreddit — style | niche | Status: pending
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

                # Capture the entire block until next "---"
                block_lines = [line]
                title = ""
                i += 1
                while i < len(lines) and not lines[i].startswith("---"):
                    block_lines.append(lines[i])
                    title_match = title_pattern.match(lines[i])
                    if title_match:
                        title = title_match.group(1).strip()
                    i += 1
                # Include the separator
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
        """Move posts with status=published to traffic_archive.md.

        Rewrites traffic_queue.md with only pending posts.
        Returns count of archived posts.
        """
        posts = self._parse_queue_posts()
        published = [p for p in posts if p["status"] == "published"]
        pending = [p for p in posts if p["status"] == "pending"]

        if not published:
            return 0

        # Append published posts to archive
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

        # Rewrite queue with only pending posts
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
        """Extract hashes of existing posts (title+subreddit) from traffic_queue.md."""
        if not TRAFFIC_QUEUE_PATH.exists():
            return set()
        try:
            content = TRAFFIC_QUEUE_PATH.read_text(encoding="utf-8")
        except OSError:
            return set()

        hashes: set[str] = set()
        # Pattern: ## [timestamp] r/subreddit — style
        # Followed by **Título:** title
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
        """Append posts (+ tweets) to traffic_queue.md in copy-paste-ready Markdown.

        Skips posts that already exist (same title + subreddit).
        """
        existing_hashes = self._get_existing_post_hashes()
        lines: list[str] = []
        skipped = 0

        for post in posts:
            # Check for duplicate
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
            niche = post.get("niche", "?")
            gumroad_url = post.get("gumroad_url", "")
            body = post.get("body", "")
            score = post.get("score_estimado", "?")
            tweet = post.get("tweet", {})
            tweet_text = tweet.get("text", "")
            tweet_url = tweet.get("url", "")
            tweet_sim = tweet.get("simulation", True)

            # --- Reddit section ---
            lines.append(f"## [{ts}] r/{sub} — {style} | {niche} | Status: pending")
            lines.append("")
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

            # --- Discord section (only when channels were targeted) ---
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

        # Log skipped duplicates
        if skipped:
            logger.info("[%s] Skipped %d duplicate post(s)", self.name, skipped)

        # Nothing new to write
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
