"""Demonstrate trimming a verbose order lookup before passing it downstream."""
import json

order = {
    "id": "ORD-558102",
    "status": "delivered",
    "delivered_on": "2026-05-08",
    "total_usd": 487.32,
    "items_count": 3,
    "is_returnable": True,
    "customer_name": "Example Customer",
    "shipping_address": {"line1": "Example Street", "city": "Example City"},
    "billing_address": {"line1": "Billing Street", "city": "Example City"},
    "payment_method": "card",
    "currency": "USD",
    "warehouse_id": "WH-12",
    "carrier": "Example Carrier",
    "tracking_number": "TRACK-12345",
    "internal_risk_score": 0.12,
    "audit_log": [{"event": "packed"}, {"event": "shipped"}],
}
for i in range(1, 36):
    order[f"internal_metadata_{i}"] = f"metadata-{i}"

relevant_fields = [
    "id", "status", "delivered_on", "total_usd", "items_count", "is_returnable"
]
filtered = {key: order[key] for key in relevant_fields}

raw_json = json.dumps(order, indent=2)
filtered_json = json.dumps(filtered, indent=2)
print("=== VERBOSE TOOL RESULT ===")
print(raw_json)
print("Original field count:", len(order))
print("Original JSON characters:", len(raw_json))
print("\n=== FILTERED RESULT ===")
print(filtered_json)
print("Fields retained:", len(filtered))
print("Filtered JSON characters:", len(filtered_json))
