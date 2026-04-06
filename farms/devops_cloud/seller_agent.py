"""DevOps Cloud Seller Agent — specialized seller for DevOps cheat sheets."""

from farms.seller_agent import SellerAgent as BaseSellerAgent

DEFAULT_STRATEGY: dict = {
    "primary_channel": "google_drive",
    "pricing_model": "fixed",
    "base_price": 24.0,
    "discount_threshold": 3,
    "discount_rate": 0.1,
    "listing_quality": 0.85,
    "target_audience": "DevOps engineers",
    "bundle_strategy": False,
}


class DevOpsSellerAgent(BaseSellerAgent):
    """Seller agent specialized in DevOps cheat sheet distribution via Google Drive."""

    def __init__(self, farm_id: str, strategy: dict | None = None) -> None:
        merged_strategy = dict(DEFAULT_STRATEGY)
        if strategy:
            merged_strategy.update(strategy)
        super().__init__(farm_id=farm_id, strategy=merged_strategy)
