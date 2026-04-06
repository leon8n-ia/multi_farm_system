"""Mobile Dev Seller Agent — specialized seller for mobile development resources."""

from farms.seller_agent import SellerAgent as BaseSellerAgent

DEFAULT_STRATEGY: dict = {
    "primary_channel": "google_drive",
    "pricing_model": "fixed",
    "base_price": 34.0,
    "target_audience": "mobile developers",
    "bundle_strategy": False,
}


class MobileDevSellerAgent(BaseSellerAgent):
    """Seller agent specialized in mobile dev resource distribution via Google Drive."""

    def __init__(self, farm_id: str, strategy: dict | None = None) -> None:
        merged_strategy = dict(DEFAULT_STRATEGY)
        if strategy:
            merged_strategy.update(strategy)
        super().__init__(farm_id=farm_id, strategy=merged_strategy)
