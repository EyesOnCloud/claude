"""Agent SDK hooks: PreToolUse (gate + policy), PostToolUse (normalization), subagent tracking."""
import json
from datetime import datetime, timezone

from claude_agent_sdk import HookMatcher

from support_tools import T

STATE = {"verified_customer_id": None}
STATUS = {1: "pending", 2: "shipped", 3: "delivered", 4: "delivered_damaged"}
REFUND_LIMIT = 500


def deny(input_data, reason):
    return {"hookSpecificOutput": {"hookEventName": input_data["hook_event_name"],
                                   "permissionDecision": "deny", "permissionDecisionReason": reason}}


async def gate_and_policy(input_data, tool_use_id, context):
    """PreToolUse: deterministic enforcement."""
    name, args = input_data["tool_name"], input_data["tool_input"]
    who = input_data.get("agent_type") or "main"
    if name in (T("lookup_order"), T("process_refund")) and not STATE["verified_customer_id"]:
        print(f"  [PreToolUse] DENY {name} ({who}): customer not verified")
        return deny(input_data, "Call get_customer and verify the customer first.")
    if name == T("process_refund") and float(args.get("amount", 0)) > REFUND_LIMIT:
        print(f"  [PreToolUse] DENY refund {args.get('amount')}: over ${REFUND_LIMIT}")
        return deny(input_data, f"Refunds over ${REFUND_LIMIT} require a human. Do not retry. Call "
                                "escalate_to_human with customer_id, root_cause, refund_amount, recommended_action.")
    print(f"  [PreToolUse] allow {name} ({who})")
    return {}


def find_json(resp):
    """The tool_response shape varies; dig out the JSON text our tool returned."""
    if isinstance(resp, str):
        try:
            return json.loads(resp)
        except ValueError:
            return None
    if isinstance(resp, dict):
        if "text" in resp:
            return find_json(resp["text"])
        resp = resp.get("content", [])
    if isinstance(resp, list):
        for item in resp:
            found = find_json(item)
            if found is not None:
                return found
    return None


def normalize(data):
    data = dict(data)
    if isinstance(data.get("created"), int):
        data["created"] = datetime.fromtimestamp(data["created"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(data.get("status"), int):
        data["status"] = STATUS.get(data["status"], "unknown")
    if isinstance(data.get("placed_at"), str):
        data["placed_at"] = (datetime.fromisoformat(data["placed_at"].replace("Z", "+00:00"))
                             .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return data


async def normalize_results(input_data, tool_use_id, context):
    """PostToolUse: open the gate on a verified customer, and normalize data before Claude reads it."""
    data = find_json(input_data.get("tool_response"))
    if not isinstance(data, dict):
        return {}
    if input_data["tool_name"] == T("get_customer") and data.get("verified") is True:
        STATE["verified_customer_id"] = data["cust_id"]
    clean = normalize(data)
    print(f"  [PostToolUse] normalized {input_data['tool_name']}: {json.dumps(clean)[:100]}")
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "updatedToolOutput": [{"type": "text", "text": json.dumps(clean)}]}}


async def track_subagents(input_data, tool_use_id, context):
    print(f"  [{input_data['hook_event_name']}] {input_data.get('agent_type', '')}")
    return {}


HOOKS = {
    "PreToolUse": [HookMatcher(matcher="^mcp__support__", hooks=[gate_and_policy])],
    "PostToolUse": [HookMatcher(matcher="^mcp__support__", hooks=[normalize_results])],
    "SubagentStart": [HookMatcher(hooks=[track_subagents])],
    "SubagentStop": [HookMatcher(hooks=[track_subagents])],
}
