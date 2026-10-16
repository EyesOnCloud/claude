"""Deterministic hooks.
pre-hook:  hook(name, args, state)   -> None to allow, or an error dict to BLOCK the tool call
post-hook: hook(name, result, state) -> the (possibly transformed) result Claude will see"""
from tools import ORDERS

REGISTRY = {"pre": {}, "post": {}}


def pre_hook(group):
    def register(fn):
        REGISTRY["pre"].setdefault(group, []).append(fn)
        return fn
    return register


def post_hook(group):
    def register(fn):
        REGISTRY["post"].setdefault(group, []).append(fn)
        return fn
    return register


def load_hooks(groups):
    pre, post = [], []
    known = set(REGISTRY["pre"]) | set(REGISTRY["post"])
    for g in (x.strip() for x in groups if x.strip()):
        if g not in known:
            raise SystemExit(f"Unknown hook group '{g}'. Known groups: {sorted(known)}")
        pre += REGISTRY["pre"].get(g, [])
        post += REGISTRY["post"].get(g, [])
    return pre, post


# ---------------- Step 1.5: prerequisite gate (TS 1.4) ----------------
ACCOUNT_TOOLS = {"lookup_order", "track_shipment", "process_refund"}


@post_hook("gate")
def remember_verified_customer(name, result, state):
    if name == "get_customer" and result.get("verified") is True:
        state["verified_customer_id"] = result["cust_id"]          # the gate opens ONLY here
    return result


@pre_hook("gate")
def require_verified_customer(name, args, state):
    if name not in ACCOUNT_TOOLS:
        return None
    if not state["verified_customer_id"]:
        return {"error": "BLOCKED_PREREQUISITE",
                "message": "No verified customer in this session. Call get_customer first."}
    order = ORDERS.get(args.get("order_id"))
    if order and order["customer"] != state["verified_customer_id"]:
        return {"error": "BLOCKED_NOT_OWNER",
                "message": "That order does not belong to the verified customer."}
    if name == "process_refund" and args.get("customer_id") != state["verified_customer_id"]:
        return {"error": "BLOCKED_CUSTOMER_MISMATCH",
                "message": "Refunds may only go to the verified customer."}
    return None
    
# ---------------- refund policy (TS 1.5) ----------------
REFUND_LIMIT = 500.00


@pre_hook("refund_limit")
def block_large_refunds(name, args, state):
    if name == "process_refund" and float(args.get("amount", 0)) > REFUND_LIMIT:
        return {"error": "BLOCKED_POLICY",
                "message": f"Refunds over ${REFUND_LIMIT:.0f} need human approval. Do not retry. "
                           "Call escalate_to_human with a complete handoff instead."}
    return None

# ---------------- data normalization (TS 1.5) ----------------
from datetime import datetime, timezone

STATUS_CODES = {1: "pending", 2: "shipped", 3: "delivered", 4: "delivered_damaged", 5: "cancelled"}
SHIP_STATES = {"INT": "in_transit", "DLV": "delivered", "DMG": "damaged_in_transit", "RTO": "returned"}


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@post_hook("normalize")
def normalize_formats(name, result, state):
    r = dict(result)
    if isinstance(r.get("created"), int):                       # Unix seconds
        r["created"] = _utc(datetime.fromtimestamp(r["created"], tz=timezone.utc))
    if isinstance(r.get("status"), int):                        # numeric status code
        r["status"] = STATUS_CODES.get(r["status"], f"unknown({r['status']})")
    if isinstance(r.get("placed_at"), str):                     # ISO with offset or Z
        r["placed_at"] = _utc(datetime.fromisoformat(r["placed_at"].replace("Z", "+00:00")))
    if "last_scan_ms" in r:                                     # epoch milliseconds
        r["last_scan_at"] = _utc(datetime.fromtimestamp(r.pop("last_scan_ms") / 1000, tz=timezone.utc))
    if r.get("state") in SHIP_STATES:                           # string carrier codes
        r["state"] = SHIP_STATES[r["state"]]
    return r
