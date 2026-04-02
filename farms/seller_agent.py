"""Generic SellerAgent used by AutoReports, ProductListing and MonetizedContent farms.

The selling strategy is injected at construction time so each farm can define
its own DEFAULT_STRATEGY without subclassing.
"""
from config import INITIAL_CREDITS


class SellerAgent:
    def __init__(self, farm_id: str, strategy: dict, credits: float = INITIAL_CREDITS) -> None:
        self.farm_id = farm_id
        self.credits = credits
        self.sales_history: list[dict] = []
        self.strategy: dict = dict(strategy)
        self.total_revenue: float = 0.0
        self.conversion_rate: float = 0.0
        self.avg_price: float = 0.0

    def prepare_listing(self, item) -> dict:
        """Build a marketplace listing dict.  *item* may be str, dict, or any object."""
        successful_sales = sum(1 for s in self.sales_history if s.get("sold"))
        apply_discount = successful_sales < self.strategy["discount_threshold"]
        price = self.strategy["base_price"]
        if apply_discount:
            price *= 1 - self.strategy["discount_rate"]

        if isinstance(item, str):
            item_summary = item[:80] + ("..." if len(item) > 80 else "")
        elif isinstance(item, dict):
            item_summary = item.get("title", str(item))[:80]
        else:
            item_summary = str(item)[:80]

        return {
            "channel": self.strategy["primary_channel"],
            "price": round(price, 2),
            "listing_quality": self.strategy["listing_quality"],
            "target_audience": self.strategy["target_audience"],
            "bundle": self.strategy["bundle_strategy"],
            "item_summary": item_summary,
            "title": item_summary,
            "description": item_summary,
        }

    def calculate_seller_score(self, cycle_results: dict) -> float:
        """revenue*10 + items_sold*5 + conversion_rate*20 - items_expired*3 - credits_spent*0.5"""
        return (
            cycle_results.get("revenue", 0) * 10
            + cycle_results.get("items_sold", 0) * 5
            + cycle_results.get("conversion_rate", 0) * 20
            - cycle_results.get("items_expired", 0) * 3
            - cycle_results.get("credits_spent", 0) * 0.5
        )

    def update_strategy(self, feedback: dict) -> None:
        self.strategy.update(feedback)

    def report_to_farm(self) -> dict:
        successful_sales = sum(1 for s in self.sales_history if s.get("sold"))
        return {
            "farm_id": self.farm_id,
            "total_revenue": self.total_revenue,
            "conversion_rate": self.conversion_rate,
            "avg_price": self.avg_price,
            "total_sales": successful_sales,
            "credits": self.credits,
            "strategy": dict(self.strategy),
        }
