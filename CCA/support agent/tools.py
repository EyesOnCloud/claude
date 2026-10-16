"""Mock company backends + the tool schemas Claude sees.
Formats are deliberately inconsistent: Unix seconds, epoch milliseconds,
ISO strings with offsets, numeric status codes and string codes."""

CUSTOMERS = {
    "asha@example.com": {"cust_id": "C-1001", "name": "Asha Rao", "verified": True, "created": 1688169600},
    "ben@example.com": {"cust_id": "C-1002", "name": "Ben Ortiz", "verified": True, "created": 1717200000},
    "eve@example.com": {"cust_id": "C-1003", "name": "Eve Smith", "verified": False, "created": 1725148800},
}
ORDERS = {
    "O-501": {"customer": "C-1001", "amount": 129.00, "status": 3, "item": "Bluetooth headphones",
              "placed_at": "2026-09-28T10:15:00+05:30"},
    "O-502": {"customer": "C-1001", "amount": 899.00, "status": 4, "item": "27-inch monitor",
              "placed_at": "2026-10-02T18:40:00+05:30"},
    "O-601": {"customer": "C-1002", "amount": 45.50, "status": 2, "item": "USB-C cable pack",
              "placed_at": "2026-10-10T09:00:00Z"},
}
SHIPMENTS = {
    "O-501": {"carrier": "BlueDart", "last_scan_ms": 1790985600000, "state": "DLV"},
    "O-502": {"carrier": "Delhivery", "last_scan_ms": 1791158400000, "state": "DMG"},
    "O-601": {"carrier": "DTDC", "last_scan_ms": 1791676800000, "state": "INT"},
}
REFUNDS_ISSUED = []
ESCALATIONS = []


def get_customer(email):
    c = CUSTOMERS.get(email.lower().strip())
    return dict(c) if c else {"error": "customer_not_found", "email": email}


def lookup_order(order_id):
    o = ORDERS.get(order_id)
    return {"order_id": order_id, **o} if o else {"error": "order_not_found", "order_id": order_id}


def track_shipment(order_id):
    s = SHIPMENTS.get(order_id)
    return {"order_id": order_id, **s} if s else {"error": "no_shipment", "order_id": order_id}


def process_refund(customer_id, order_id, amount, reason):
    rec = {"refund_id": f"R-{9001 + len(REFUNDS_ISSUED)}", "customer_id": customer_id,
           "order_id": order_id, "amount": amount, "reason": reason}
    REFUNDS_ISSUED.append(rec)
    return {"status": "refund_issued", **rec}


def escalate_to_human(**handoff):
    ESCALATIONS.append(handoff)
    return {"status": "escalated", "ticket": f"ESC-{300 + len(ESCALATIONS)}"}


IMPLS = {"get_customer": get_customer, "lookup_order": lookup_order, "track_shipment": track_shipment,
         "process_refund": process_refund, "escalate_to_human": escalate_to_human}


def run_tool(name, args):
    if name not in IMPLS:
        return {"error": f"unknown tool {name}"}
    return IMPLS[name](**args)


def _schema(name, description, props, required):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required}}


S = {"type": "string"}
TOOLS = [
    _schema("get_customer", "Look up and verify a customer by email. Call this before any account action.",
            {"email": S}, ["email"]),
    _schema("lookup_order", "Get an order's amount, item, status and timestamp by order ID (e.g. O-501).",
            {"order_id": S}, ["order_id"]),
    _schema("track_shipment", "Get carrier tracking state and last scan time for an order.",
            {"order_id": S}, ["order_id"]),
    _schema("process_refund", "Issue a refund for an order to a verified customer.",
            {"customer_id": S, "order_id": S, "amount": {"type": "number"}, "reason": S},
            ["customer_id", "order_id", "amount", "reason"]),
    _schema("escalate_to_human",
            "Hand the case to a human agent who CANNOT see this conversation. The handoff must be self-contained.",
            {"customer_id": S, "customer_name": S, "issue_summary": S, "root_cause": S,
             "order_ids": {"type": "array", "items": S}, "refund_amount_requested": {"type": "number"},
             "actions_already_taken": {"type": "array", "items": S}, "recommended_action": S,
             "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
            ["customer_id", "issue_summary", "root_cause", "recommended_action", "priority"]),
]
