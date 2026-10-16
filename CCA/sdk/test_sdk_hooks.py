"""Run:  python -m pytest -v test_sdk_hooks.py   (or: python test_sdk_hooks.py)"""
import asyncio
import json

import sdk_hooks
from support_tools import T


def run(coro):
    return asyncio.run(coro)


def pre(tool, args):
    return run(sdk_hooks.gate_and_policy({"hook_event_name": "PreToolUse", "tool_name": T(tool),
                                          "tool_input": args}, "id1", None))


def post(tool, payload):
    return run(sdk_hooks.normalize_results({"hook_event_name": "PostToolUse", "tool_name": T(tool),
                                            "tool_response": [{"type": "text", "text": json.dumps(payload)}]},
                                           "id1", None))


def setup_function():
    sdk_hooks.STATE["verified_customer_id"] = None


def test_refund_denied_before_verification():
    out = pre("process_refund", {"amount": 10})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_verified_customer_opens_gate():
    post("get_customer", {"cust_id": "C-1001", "verified": True, "created": 1688169600})
    assert sdk_hooks.STATE["verified_customer_id"] == "C-1001"
    assert pre("lookup_order", {"order_id": "O-501"}) == {}


def test_unverified_customer_keeps_gate_closed():
    post("get_customer", {"cust_id": "C-1003", "verified": False, "created": 1725148800})
    assert pre("lookup_order", {"order_id": "O-501"})["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_refund_over_limit_denied_even_when_verified():
    sdk_hooks.STATE["verified_customer_id"] = "C-1001"
    out = pre("process_refund", {"amount": 899})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "escalate_to_human" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_post_hook_rewrites_output():
    out = post("lookup_order", {"order_id": "O-502", "status": 4, "placed_at": "2026-10-02T18:40:00+05:30"})
    data = json.loads(out["hookSpecificOutput"]["updatedToolOutput"][0]["text"])
    assert data["status"] == "delivered_damaged"
    assert data["placed_at"] == "2026-10-02T13:10:00Z"


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            setup_function()
            f()
            print(f"PASS {n}")
