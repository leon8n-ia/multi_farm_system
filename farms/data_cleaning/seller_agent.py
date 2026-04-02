from config import COST_SELLER_LISTING, INITIAL_CREDITS


class SellerAgent:
    DEFAULT_STRATEGY: dict = {
        "primary_channel": "gumroad",
        "pricing_model": "fixed",
        "base_price": 9.0,
        "discount_threshold": 3,
        "discount_rate": 0.20,
        "listing_quality": "high",
        "target_audience": "data scientists and ML engineers",
        "bundle_strategy": False,
        "niche_focus": "ecommerce",
        "output_format": "csv",
    }

    def __init__(self, farm_id: str, credits: float = INITIAL_CREDITS) -> None:
        self.farm_id = farm_id
        self.credits = credits
        self.sales_history: list[dict] = []
        self.strategy: dict = dict(self.DEFAULT_STRATEGY)
        self.total_revenue: float = 0.0
        self.conversion_rate: float = 0.0
        self.avg_price: float = 0.0

    # ------------------------------------------------------------------

    def prepare_listing(self, item) -> dict:
        """Build a marketplace listing dict for *item*.

        Applies a discount until the agent accumulates at least
        ``discount_threshold`` successful sales (intro pricing).
        """
        successful_sales = sum(1 for s in self.sales_history if s.get("sold"))
        apply_discount = successful_sales < self.strategy["discount_threshold"]
        price = self.strategy["base_price"]
        if apply_discount:
            price *= 1 - self.strategy["discount_rate"]

        niche = self.strategy.get("niche_focus", "general")
        output_fmt = self.strategy.get("output_format", "csv")
        niche_label = niche.replace("_", " ").title()
        audience = self.strategy["target_audience"]

        try:
            rows, cols = len(item), len(item.columns)
            item_summary = f"Cleaned dataset: {rows} rows x {cols} cols"
            title = f"{niche_label} Cleaned Dataset — {rows}r x {cols}c [{output_fmt.upper()}]"
            description = (
                f"Production-ready {niche_label.lower()} dataset: {rows} rows, {cols} columns. "
                f"Normalized, deduplicated, null-free. "
                f"Format: {output_fmt.upper()}. "
                f"For {audience}."
            )
        except Exception:
            item_summary = str(item)
            title = f"{niche_label} Dataset [{output_fmt.upper()}]"
            description = (
                f"Cleaned {niche_label.lower()} dataset in {output_fmt.upper()} format. "
                f"For {audience}."
            )

        return {
            "channel": self.strategy["primary_channel"],
            "price": round(price, 2),
            "listing_quality": self.strategy["listing_quality"],
            "target_audience": audience,
            "bundle": self.strategy["bundle_strategy"],
            "item_summary": item_summary,
            "title": title,
            "description": description,
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
        """Merge *feedback* into the current strategy."""
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
