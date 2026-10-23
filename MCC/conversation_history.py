"""Compare complete conversation history with an incomplete latest-turn-only payload."""
import json

complete_messages = [
    {
        "role": "user",
        "content": (
            "My order is ORD-558102. The charge was $487.32 on March 3, 2026, "
            "after I cancelled the service on February 28, 2026."
        ),
    },
    {
        "role": "assistant",
        "content": "I will review the charge and cancellation details.",
    },
    {"role": "user", "content": "What exact amount am I disputing?"},
]
latest_only_messages = [
    {"role": "user", "content": "What exact amount am I disputing?"}
]

print("=== COMPLETE RELEVANT HISTORY ===")
print(json.dumps({"messages": complete_messages}, indent=2))
print("\n=== LATEST TURN ONLY (CONTEXT MISSING) ===")
print(json.dumps({"messages": latest_only_messages}, indent=2))
print("\nNote: This script displays example payloads; it does not submit an API request.")
