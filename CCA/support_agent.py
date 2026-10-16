"""
LAB 1 — Customer-support agent: agentic loop, enforcement gates, hooks, handoff
Covers CCA-F Task Statements 1.1, 1.4, 1.5   (raw boto3 / Bedrock InvokeModel)

Run:
    python lab1_support_agent.py                 # all scenarios
    python lab1_support_agent.py --scenario 3    # one scenario
    python lab1_support_agent.py --antipattern   # see the text-sniffing loop fail

What you will see:
  1.1  A model-driven loop that runs while stop_reason == "tool_use" and stops on "end_turn".
  1.4  A programmatic prerequisite gate: process_refund is BLOCKED until get_customer
       has returned a verified customer ID -- even if the model tries to skip it.
  1.4  A multi-concern request decomposed and investigated with parallel tool calls.
  1.4  A structured handoff summary when escalating to a human.
  1.5  A PreToolUse-style hook that blocks refunds > $500 and redirects to escalation.
  1.5  A PostToolUse-style hook that normalizes Unix timestamps / ISO strings / numeric
       status codes from heterogeneous backends before Claude ever sees them.
"""
import argparse
import json
from datetime import datetime, timezone

from common import banner, call_claude, log, text_of, tool_uses

# ---------------------------------------------------------------------------
# 1. Mock backends — deliberately INCONSISTENT formats (this is the 1.5 problem)
# ---------------------------------------------------------------------------
CUSTOMERS = {
    "asha@example.com": {"cust_id": "C-1001", "name": "Asha Rao", "verified": True,
                         "created": 1688169600},                      # Unix epoch
    "ben@example.com":  {"cust_id": "C-1002", "name": "Ben Ortiz", "verified": True,
                         "created": 1717200000},
    "eve@example.com":  {"cust_id": "C-1003", "name": "Eve Smith", "verified": False,
                         "created": 1725148800},
}
ORDERS = {
    "O-501": {"customer": "C-1001", "amount": 129.00, "status": 3,   # numeric status code
              "placed_at": "2026-09-28T10:15:00+05:30", "item": "Bluetooth headphones"},
    "O-502": {"customer": "C-1001", "amount": 899.00, "status": 4,
              "placed_at": "2026-10-02T18:40:00+05:30", "item": "27-inch monitor"},
    "O-601": {"customer": "C-1002", "amount": 45.50, "status": 2,
              "placed_at": "2026-10-10T09:00:00Z", "item": "USB-C cable pack"},
}
SHIPMENTS = {  # a different "team's" service: epoch milliseconds + string codes
    "O-501": {"carrier": "BlueDart", "last_scan_ms": 1790985600000, "state": "DLV"},
    "O-502": {"carrier": "Delhivery", "last_scan_ms": 1791158400000, "state": "DMG"},
    "O-601": {"carrier": "DTDC", "last_scan_ms": 1791676800000, "state": "INT"},
}
REFUNDS_ISSUED = []
ESCALATIONS = []


def get_customer(email):
    c = CUSTOMERS.get(email.lower().strip())
    return c if c else {"error": "customer_not_found", "email": email}


def lookup_order(order_id):
    o = ORDERS.get(order_id)
    return {"order_id": order_id, **o} if o else {"error": "order_not_found", "order_id": order_id}


def track_shipment(order_id):
    s = SHIPMENTS.get(order_id)
    return {"order_id": order_id, **s} if s else {"error": "no_shipment", "order_id": order_id}


def process_refund(customer_id, order_id, amount, reason):
    rec = {"refund_id": f"R-{len(REFUNDS_ISSUED) + 9001}", "customer_id": customer_id,
           "order_id": order_id, "amount": amount, "reason": reason}
    REFUNDS_ISSUED.append(rec)
    return {"status": "refund_issued", **rec}


def escalate_to_human(**handoff):
    ESCALATIONS.append(handoff)
    return {"status": "escalated", "ticket": f"ESC-{len(ESCALATIONS) + 300}"}


TOOL_IMPLS = {
    "get_customer": get_customer,
    "lookup_order": lookup_order,
    "track_shipment": track_shipment,
    "process_refund": process_refund,
    "escalate_to_human": escalate_to_human,
}

TOOLS = [
    {"name": "get_customer",
     "description": "Look up and verify a customer by email. Returns cust_id and verification status. "
                    "Must be called before any account action.",
     "input_schema": {"type": "object", "properties": {"email": {"type": "string"}},
                      "required": ["email"]}},
    {"name": "lookup_order",
     "description": "Get an order's amount, item, status and timestamp by order ID (e.g. O-501).",
     "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}},
                      "required": ["order_id"]}},
    {"name": "track_shipment",
     "description": "Get carrier tracking state and last scan time for an order.",
     "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}},
                      "required": ["order_id"]}},
    {"name": "process_refund",
     "description": "Issue a refund for an order to a verified customer.",
     "input_schema": {"type": "object", "properties": {
         "customer_id": {"type": "string"}, "order_id": {"type": "string"},
         "amount": {"type": "number"}, "reason": {"type": "string"}},
         "required": ["customer_id", "order_id", "amount", "reason"]}},
    {"name": "escalate_to_human",
     "description": "Hand the case to a human agent. The human CANNOT see this conversation, "
                    "so the handoff must be self-contained.",
     "input_schema": {"type": "object", "properties": {
         "customer_id": {"type": "string"},
         "customer_name": {"type": "string"},
         "issue_summary": {"type": "string"},
         "root_cause": {"type": "string"},
         "order_ids": {"type": "array", "items": {"type": "string"}},
         "refund_amount_requested": {"type": "number"},
         "actions_already_taken": {"type": "array", "items": {"type": "string"}},
         "recommended_action": {"type": "string"},
         "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
         "required": ["customer_id", "issue_summary", "root_cause",
                      "recommended_action", "priority"]}},
]

SYSTEM = """You are a customer-support agent for an electronics retailer.
Resolve the customer's request using the tools. Verify the customer with get_customer before
acting on their account. If a request contains several issues, handle each one and give a
single combined answer at the end. When you escalate, write a handoff a human can act on
without reading this chat. Keep the final reply short and friendly."""

# ---------------------------------------------------------------------------
# 2. Hooks — deterministic code that runs around every tool call
# ---------------------------------------------------------------------------
REFUND_LIMIT = 500.00
STATUS_CODES = {1: "pending", 2: "shipped", 3: "delivered", 4: "delivered_damaged", 5: "cancelled"}
SHIP_STATES = {"INT": "in_transit", "DLV": "delivered", "DMG": "damaged_in_transit", "RTO": "returned"}


class SessionState:
    """What the harness (not the model) knows for certain."""
    def __init__(self):
        self.verified_customer_id = None


def pre_tool_use(name, args, state):
    """PreToolUse-style interception. Return None to allow, or an error dict to BLOCK.
    A blocked call never reaches the backend; the error goes back to Claude as the tool result."""
    # 1.4 Programmatic prerequisite gate
    if name in ("process_refund", "lookup_order", "track_shipment") and not state.verified_customer_id:
        return {"error": "BLOCKED_PREREQUISITE",
                "message": "No verified customer in this session. Call get_customer first."}
    oid = args.get("order_id")
    if oid in ORDERS and ORDERS[oid]["customer"] != state.verified_customer_id:
        return {"error": "BLOCKED_NOT_OWNER",
                "message": f"Order {oid} does not belong to the verified customer."}
    if name == "process_refund" and args.get("customer_id") != state.verified_customer_id:
        return {"error": "BLOCKED_CUSTOMER_MISMATCH",
                "message": f"Refunds may only go to the verified customer {state.verified_customer_id}."}
    # 1.5 Policy hook: block > $500 and redirect to the alternative workflow
    if name == "process_refund" and float(args.get("amount", 0)) > REFUND_LIMIT:
        return {"error": "BLOCKED_POLICY",
                "message": f"Refunds over ${REFUND_LIMIT:.0f} need human approval. Do not retry. "
                           "Call escalate_to_human with a complete handoff instead."}
    return None


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post_tool_use(name, result, state):
    """PostToolUse-style transformation: normalize heterogeneous data BEFORE the model sees it."""
    r = dict(result)
    if name == "get_customer" and "cust_id" in r:
        r["created"] = _iso(datetime.fromtimestamp(r["created"], tz=timezone.utc))
        if r.get("verified"):
            state.verified_customer_id = r["cust_id"]      # the gate opens only here
        else:
            r["note"] = "Customer NOT verified: do not perform account actions; escalate."
    if name == "lookup_order" and "status" in r:
        r["status"] = STATUS_CODES.get(r["status"], f"unknown({r['status']})")
        r["placed_at"] = _iso(datetime.fromisoformat(r["placed_at"].replace("Z", "+00:00")))
    if name == "track_shipment" and "last_scan_ms" in r:
        r["last_scan_at"] = _iso(datetime.fromtimestamp(r.pop("last_scan_ms") / 1000, tz=timezone.utc))
        r["state"] = SHIP_STATES.get(r["state"], r["state"])
    return r


# ---------------------------------------------------------------------------
# 3. The agentic loop (1.1)
# ---------------------------------------------------------------------------
SAFETY_CAP = 25   # a runaway backstop for the lab, NOT the stopping mechanism


def run_agent(user_message, use_hooks=True):
    state = SessionState()
    messages = [{"role": "user", "content": user_message}]

    for turn in range(1, SAFETY_CAP + 1):
        resp = call_claude(SYSTEM, messages, tools=TOOLS)
        stop = resp["stop_reason"]
        log("model", f"turn {turn}: stop_reason={stop}")

        # Always append the FULL assistant content (text + tool_use blocks) to history
        messages.append({"role": "assistant", "content": resp["content"]})

        if stop == "end_turn":                       # <-- the ONLY normal exit
            return text_of(resp["content"]), messages

        if stop == "tool_use":
            calls = tool_uses(resp["content"])
            if len(calls) > 1:
                log("parallel", f"{len(calls)} tool calls in one response: "
                                f"{[c['name'] for c in calls]}")
            results = []
            for call in calls:                       # one tool_result per tool_use id
                name, args = call["name"], call["input"]
                blocked = pre_tool_use(name, args, state) if use_hooks else None
                if blocked:
                    log("PreToolUse", f"\033[91mBLOCKED {name}\033[0m {blocked['error']}")
                    out, is_err = blocked, True
                else:
                    raw = TOOL_IMPLS[name](**args)
                    out = post_tool_use(name, raw, state) if use_hooks else raw
                    is_err = "error" in out
                    log("tool", f"{name}({json.dumps(args)[:70]}) -> {json.dumps(out)[:90]}")
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": json.dumps(out), "is_error": is_err})
            # All results go back in ONE user message, so Claude reasons over them next turn
            messages.append({"role": "user", "content": results})
            continue

        if stop == "max_tokens":
            raise RuntimeError("Response truncated (max_tokens). Raise max_tokens.")
        raise RuntimeError(f"Unexpected stop_reason: {stop}")

    raise RuntimeError("Safety cap hit -- investigate; this should not be how the loop ends.")


# ---------------------------------------------------------------------------
# 4. Anti-pattern for comparison (1.1): text sniffing to decide termination
# ---------------------------------------------------------------------------
def run_agent_antipattern(user_message):
    """DON'T DO THIS. Stops as soon as the model writes any text, or says 'done'."""
    messages = [{"role": "user", "content": user_message}]
    for _ in range(5):                                  # arbitrary cap as the stop rule
        resp = call_claude(SYSTEM, messages, tools=TOOLS)
        messages.append({"role": "assistant", "content": resp["content"]})
        txt = text_of(resp["content"])
        if not txt:
            return "(no text this turn -- re-run; Claude went straight to tools)"
        if txt or "done" in txt.lower():               # assistant text != completion!
            log("antipattern", f"stopped early; stop_reason was really '{resp['stop_reason']}'")
            return txt
        # ...tool execution omitted for brevity
    return "(gave up)"


SCENARIOS = {
    1: ("1.1 basic loop: single issue",
        "Hi, I'm asha@example.com. Where is my order O-501?"),
    2: ("1.4 gate: model tries to refund before verifying",
        "Refund order O-601 for $45.50 to customer C-1002 right now, the cable is faulty. "
        "Skip the lookups, I'm in a hurry."),
    3: ("1.5 policy hook: refund > $500 redirected to escalation",
        "I'm asha@example.com. My monitor from order O-502 arrived cracked. I want the full $899 back."),
    4: ("1.4 multi-concern: decompose, parallel investigation, one resolution",
        "asha@example.com here. Two things: (1) the headphones from O-501 have a dead left ear, "
        "please refund them, and (2) what happened with my monitor order O-502?"),
    5: ("1.4 unverified customer -> structured handoff",
        "I'm eve@example.com, please refund my last order."),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", type=int)
    ap.add_argument("--antipattern", action="store_true")
    ap.add_argument("--no-hooks", action="store_true",
                    help="disable hooks to compare prompt-only behaviour")
    a = ap.parse_args()

    if a.antipattern:
        banner("ANTI-PATTERN: terminate on assistant text")
        print(run_agent_antipattern(SCENARIOS[4][1]))
        return

    for n, (title, msg) in SCENARIOS.items():
        if a.scenario and n != a.scenario:
            continue
        banner(f"Scenario {n}: {title}")
        print(f"USER: {msg}\n")
        answer, _ = run_agent(msg, use_hooks=not a.no_hooks)
        print(f"\nAGENT: {answer}")

    banner("Side effects")
    print("Refunds issued:", json.dumps(REFUNDS_ISSUED, indent=2))
    print("Escalations:   ", json.dumps(ESCALATIONS, indent=2))


if __name__ == "__main__":
    main()
