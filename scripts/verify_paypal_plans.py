"""
Script to verify PayPal plan status and activate if needed.
"""
import sys
import json
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "access_server"))

from paypal_bridge import PayPalBridge

def main():
    # Load created plans
    plans_file = os.path.join(os.path.dirname(__file__), "paypal_plans_created.json")
    with open(plans_file) as f:
        data = json.load(f)

    bridge = PayPalBridge(sandbox=True)

    print("=" * 70)
    print("Verificando estado de planes en PayPal Sandbox")
    print("=" * 70)
    print()

    all_active = True
    results = []

    for detail in data["details"]:
        farm = detail["farm_type"]
        plan_id = detail["plan_id"]

        # GET plan details
        url = f"{bridge.base_url}/v1/billing/plans/{plan_id}"
        response = bridge._request_with_retry("GET", url)

        if response.success:
            status = response.data.get("status", "UNKNOWN")
            name = response.data.get("name", "N/A")
            symbol = "[OK]" if status == "ACTIVE" else "[!!]"
            print(f"{symbol} {farm:20} | {plan_id} | {status}")

            if status != "ACTIVE":
                all_active = False
                print(f"    -> Activando plan...")
                # PATCH to activate
                activate_response = bridge._request_with_retry(
                    "PATCH",
                    url,
                    json=[{"op": "replace", "path": "/status", "value": "ACTIVE"}]
                )
                if activate_response.success:
                    print(f"    -> Plan activado!")
                    status = "ACTIVE (recién activado)"
                else:
                    print(f"    -> Error: {activate_response.error}")

            results.append({
                "farm": farm,
                "plan_id": plan_id,
                "status": status
            })
        else:
            print(f"[!!] {farm:20} | {plan_id} | ERROR: {response.error}")
            all_active = False
            results.append({
                "farm": farm,
                "plan_id": plan_id,
                "status": f"ERROR: {response.error}"
            })

    print()
    print("=" * 70)
    if all_active:
        print("Todos los planes estan ACTIVE")
    else:
        print("Verificacion completada - revisar planes marcados con [!!]")
    print("=" * 70)


if __name__ == "__main__":
    main()
