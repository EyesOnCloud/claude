"""Support tools exposed to the Agent SDK. Claude sees them as mcp__support__<name>."""
import json

from claude_agent_sdk import create_sdk_mcp_server, tool

CUSTOMERS = {"asha@example.com": {"cust_id": "C-1001", "verified": True, "created": 1688169600},
             "eve@example.com": {"cust_id": "C-1003", "verified": False, "created": 1725148800}}
ORDERS = {"O-501": {"customer": "C-1001", "amount": 129.0, "status": 3, "placed_at": "2026-09-28T10:15:00+05:30"},
          "O-502": {"customer": "C-1001", "amount": 899.0, "status": 4, "placed_at": "2026-10-02T18:40:00+05:30"}}
REFUNDS, HANDOFFS = [], []


def as_text(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


@tool("get_customer", "Look up and verify a customer by email.", {"email": str})
async def get_customer(args):
    return as_text(CUSTOMERS.get(args["email"].lower(), {"error": "not_found"}))


@tool("lookup_order", "Get an order by ID (e.g. O-501).", {"order_id": str})
async def lookup_order(args):
    o = ORDERS.get(args["order_id"])
    return as_text({"order_id": args["order_id"], **o} if o else {"error": "not_found"})


@tool("process_refund", "Refund an order to a verified customer.",
      {"customer_id": str, "order_id": str, "amount": float, "reason": str})
async def process_refund(args):
    REFUNDS.append(args)
    return as_text({"status": "refund_issued", **args})


@tool("escalate_to_human", "Hand off to a human who cannot see this chat. Provide customer_id, root_cause, "
      "refund_amount and recommended_action.",
      {"customer_id": str, "root_cause": str, "refund_amount": float, "recommended_action": str})
async def escalate_to_human(args):
    HANDOFFS.append(args)
    return as_text({"status": "escalated", "ticket": f"ESC-{300 + len(HANDOFFS)}"})


server = create_sdk_mcp_server(name="support", version="1.0.0",
                               tools=[get_customer, lookup_order, process_refund, escalate_to_human])


def T(name):
    return f"mcp__support__{name}"


ALL_TOOLS = [T(n) for n in ("get_customer", "lookup_order", "process_refund", "escalate_to_human")]
