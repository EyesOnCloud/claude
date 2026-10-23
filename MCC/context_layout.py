"""Show key findings first, then issue-specific details and open questions."""
import json
from pathlib import Path

context = json.loads((Path(__file__).resolve().parent / "case_context.json").read_text())
case = context["case_facts"]
issues = context["issues"]

organized = {
    "KEY_FINDINGS": [
        f"Order {case['order_id']}: requested refund ${case['requested_refund_usd']:.2f}.",
        f"Charge date: {case['charge_date']}.",
        f"Service cancellation date: {case['service_cancellation_date']}.",
        f"Customer expectation: {case['customer_expectation']}.",
    ],
    "ISSUE_DETAILS": issues,
    "OPEN_QUESTIONS": [
        "Has the return been initiated?",
        "Has refund eligibility been confirmed?",
    ],
}
print(json.dumps(organized, indent=2))
