"""Thin wrapper around the Twitter API v2 (tweepy) for posting tweets.

Runs in **simulation mode** (no network calls) when any of the four required
environment variables are absent:
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_TOKEN_SECRET
"""
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_REQUIRED_ENV = (
    "TWITTER_API_KEY",
    "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN",
    "TWITTER_ACCESS_TOKEN_SECRET",
)

# Fallback username used when get_me() fails or in simulation
_FALLBACK_USERNAME = "MLDatasetsHub"


class TwitterBridge:
    """Post tweets via Twitter API v2.  Falls back to simulation on missing creds or errors."""

    def __init__(self) -> None:
        self.api_key: str | None = os.environ.get("TWITTER_API_KEY")
        self.api_secret: str | None = os.environ.get("TWITTER_API_SECRET")
        self.access_token: str | None = os.environ.get("TWITTER_ACCESS_TOKEN")
        self.access_token_secret: str | None = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

        self._simulation: bool = not all(
            [self.api_key, self.api_secret, self.access_token, self.access_token_secret]
        )
        self._username: str = _FALLBACK_USERNAME
        self._client = None  # lazy-initialised on first real post

        if self._simulation:
            logger.info("[TwitterBridge] Simulation mode (credentials missing).")
        else:
            self._init_client()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        try:
            import tweepy
        except ImportError:
            logger.error("[TwitterBridge] tweepy not installed — falling back to simulation.")
            self._simulation = True
            return

        self._client = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )
        # Resolve the authenticated account's username for URL construction
        try:
            me = self._client.get_me()
            if me.data:
                self._username = me.data.username
                logger.info("[TwitterBridge] Authenticated as @%s", self._username)
        except Exception as exc:
            logger.warning(
                "[TwitterBridge] get_me() failed (%s) — using fallback username @%s",
                exc, _FALLBACK_USERNAME,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def post_tweet(self, text: str) -> dict:
        """Post *text* as a tweet.

        Truncates to 280 characters if needed.
        Returns a dict with: tweet_id, url, simulation.
        """
        # Hard Twitter limit
        if len(text) > 280:
            text = text[:277] + "..."

        if self._simulation or self._client is None:
            return self._sim_result(text)

        try:
            response = self._client.create_tweet(text=text)
            tweet_id = str(response.data["id"])
            url = f"https://twitter.com/{self._username}/status/{tweet_id}"
            logger.info("[TwitterBridge] Tweet posted — %s", url)
            return {"tweet_id": tweet_id, "url": url, "simulation": False}
        except Exception as exc:
            logger.warning(
                "[TwitterBridge] create_tweet failed (%s) — simulating.", exc
            )
            return self._sim_result(text)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sim_result(self, text: str) -> dict:
        fake_id = str(int(datetime.now().timestamp() * 1000))
        return {
            "tweet_id": fake_id,
            "url": f"https://twitter.com/{_FALLBACK_USERNAME}/status/{fake_id}",
            "simulation": True,
        }
