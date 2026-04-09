"""
Script to create PayPal products and subscription plans for all farms.

Run once in sandbox to get plan IDs for PAYPAL_PLAN_MAP env var.
"""
import sys
import os
import json

# Add access_server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "access_server"))

from paypal_bridge import PayPalBridge

# Farm configurations
FARMS = [
    {
        "farm_type": "data_cleaning",
        "product_name": "Clean Dataset ML Ready",
        "description": "Monthly subscription for ML-ready clean datasets. High-quality data cleaning for machine learning projects.",
        "price_usd": 7.00
    },
    {
        "farm_type": "auto_reports",
        "product_name": "AI Financial Report",
        "description": "Monthly AI-generated financial reports and analysis. Professional insights powered by AI.",
        "price_usd": 19.00
    },
    {
        "farm_type": "product_listing",
        "product_name": "Optimized Product Listings Pack",
        "description": "Monthly pack of SEO-optimized product listings for e-commerce. Boost your sales with AI copy.",
        "price_usd": 4.00
    },
    {
        "farm_type": "monetized_content",
        "product_name": "AI Content Pack",
        "description": "Monthly AI-generated content for blogs, social media, and marketing. Fresh content every month.",
        "price_usd": 9.00
    },
    {
        "farm_type": "react_nextjs",
        "product_name": "React/Next.js Prompt Pack",
        "description": "Monthly collection of React and Next.js development prompts. Build faster with AI-assisted coding.",
        "price_usd": 39.00
    },
    {
        "farm_type": "devops_cloud",
        "product_name": "DevOps Cloud Cheat Sheet Pack",
        "description": "Monthly DevOps and cloud infrastructure cheat sheets. AWS, GCP, Azure, Kubernetes, Docker and more.",
        "price_usd": 24.00
    },
    {
        "farm_type": "mobile_dev",
        "product_name": "Mobile Dev Starter Kit",
        "description": "Monthly mobile development resources for iOS and Android. Flutter, React Native, Swift, Kotlin.",
        "price_usd": 34.00
    }
]


def main():
    print("=" * 60)
    print("Creating PayPal Products and Plans (Sandbox)")
    print("=" * 60)
    print()

    bridge = PayPalBridge(sandbox=True)

    if not bridge.enabled:
        print("ERROR: PayPal is disabled (PAYPAL_ENABLED=false)")
        print("Set PAYPAL_ENABLED=true to create real plans")
        return

    plan_map = {}
    results = []

    for farm in FARMS:
        print(f"Creating: {farm['product_name']}...")

        # Create product
        product_response = bridge.create_product(
            name=farm["product_name"],
            description=farm["description"]
        )

        if not product_response.success:
            print(f"  ERROR creating product: {product_response.error}")
            continue

        product_id = product_response.data["id"]
        print(f"  Product ID: {product_id}")

        # Create plan
        plan_response = bridge.create_plan(
            product_id=product_id,
            name=f"{farm['product_name']} - Monthly",
            price_usd=farm["price_usd"],
            interval="MONTH"
        )

        if not plan_response.success:
            print(f"  ERROR creating plan: {plan_response.error}")
            continue

        plan_id = plan_response.data["id"]
        print(f"  Plan ID: {plan_id}")
        print(f"  Price: ${farm['price_usd']}/month")
        print()

        plan_map[farm["farm_type"]] = plan_id
        results.append({
            "farm_type": farm["farm_type"],
            "product_name": farm["product_name"],
            "product_id": product_id,
            "plan_id": plan_id,
            "price_usd": farm["price_usd"]
        })

    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print()

    for r in results:
        print(f"{r['farm_type']:20} | {r['plan_id']} | ${r['price_usd']}/mo")

    print()
    print("=" * 60)
    print("PAYPAL_PLAN_MAP (copy to Render)")
    print("=" * 60)
    print()
    print(json.dumps(plan_map))
    print()

    # Also save to file for reference
    output_file = os.path.join(os.path.dirname(__file__), "paypal_plans_created.json")
    with open(output_file, "w") as f:
        json.dump({
            "plan_map": plan_map,
            "details": results
        }, f, indent=2)
    print(f"Full details saved to: {output_file}")


if __name__ == "__main__":
    main()
