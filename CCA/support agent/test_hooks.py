"""Unit tests for Lab 1 hooks. Run:  python -m pytest -v test_hooks.py   (or: python test_hooks.py)"""
from hooks import (block_large_refunds, normalize_formats, remember_verified_customer,
                   require_verified_customer)
from tools import run_tool


def fresh_state():
    return {"verified_customer_id": None}


def verify(email, state):
    remember_verified_customer("get_customer", run_tool("get_customer", {"email": email}), state)


REFUND = {"customer_id": "C-1001", "order_id": "O-501", "amount": 129, "reason": "faulty"}


def test_refund_blocked_before_verification():
    out = require_verified_customer("process_refund", REFUND, fresh_state())
    assert out["error"] == "BLOCKED_PREREQUISITE"


def test_gate_opens_after_verified_customer():
    s = fresh_state()
    verify("asha@example.com", s)
    assert s["verified_customer_id"] == "C-1001"
    assert require_verified_customer("process_refund", REFUND, s) is None


def test_unverified_customer_never_opens_gate():
    s = fresh_state()
    verify("eve@example.com", s)
    assert s["verified_customer_id"] is None
    assert require_verified_customer("lookup_order", {"order_id": "O-501"}, s)["error"] == "BLOCKED_PREREQUISITE"


def test_cannot_read_another_customers_order():
    s = fresh_state()
    verify("asha@example.com", s)
    assert require_verified_customer("lookup_order", {"order_id": "O-601"}, s)["error"] == "BLOCKED_NOT_OWNER"


def test_get_customer_is_never_gated():
    assert require_verified_customer("get_customer", {"email": "x@example.com"}, fresh_state()) is None


def test_refund_limit_blocks_over_500():
    out = block_large_refunds("process_refund", {**REFUND, "amount": 899}, fresh_state())
    assert out["error"] == "BLOCKED_POLICY"


def test_refund_limit_allows_500_and_below():
    assert block_large_refunds("process_refund", {**REFUND, "amount": 500}, fresh_state()) is None
    assert block_large_refunds("process_refund", REFUND, fresh_state()) is None


def test_normalize_customer_timestamp():
    r = normalize_formats("get_customer", run_tool("get_customer", {"email": "asha@example.com"}), {})
    assert r["created"] == "2023-07-01T00:00:00Z"


def test_normalize_order_status_and_timezone():
    r = normalize_formats("lookup_order", run_tool("lookup_order", {"order_id": "O-502"}), {})
    assert r["status"] == "delivered_damaged"
    assert r["placed_at"] == "2026-10-02T13:10:00Z"


def test_normalize_shipment_epoch_ms_and_code():
    r = normalize_formats("track_shipment", run_tool("track_shipment", {"order_id": "O-502"}), {})
    assert "last_scan_ms" not in r
    assert r["last_scan_at"] == "2026-10-05T00:00:00Z"
    assert r["state"] == "damaged_in_transit"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for n, f in tests:
        f()
        print(f"PASS {n}")
    print(f"\n{len(tests)} passed")
