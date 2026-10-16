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
