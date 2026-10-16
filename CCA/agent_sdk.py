"""
LAB 3 — Claude Agent SDK on Amazon Bedrock: AgentDefinition, subagents, SDK hooks, sessions
Covers CCA-F Task Statements 1.3, 1.5, 1.7  (and revisits 1.4 with real SDK hooks)

Labs 1 and 2 built the machinery by hand. Here the Agent SDK provides it:
the loop, the subagent tool, hooks and session storage.

Setup (see README):  pip install claude-agent-sdk
                     export CLAUDE_CODE_USE_BEDROCK=1 AWS_REGION=us-east-1
                     export ANTHROPIC_MODEL=<your Bedrock inference-profile id>

Run, in order:
    python lab3_agent_sdk.py support      # Part A: AgentDefinition + subagents + PreToolUse/PostToolUse hooks
    python lab3_agent_sdk.py analyze      # Part B1: named investigation session over ./sample_app
    python lab3_agent_sdk.py change       # Part B2: simulate a code change between work sessions
    python lab3_agent_sdk.py resume       # Part B3: resume BY NAME + tell the agent what changed
    python lab3_agent_sdk.py fork         # Part B4: fork_session -> two strategies from one baseline
    python lab3_agent_sdk.py fresh        # Part B5: new session seeded with a structured summary
    python lab3_agent_sdk.py sessions     # list saved session names

NOTE on naming: the exam guide calls the subagent tool "Task". Current Claude Code / Agent SDK
releases call it "Agent" (older ones: "Task"). We allow both so the lab works on either.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import (AgentDefinition, AssistantMessage, ClaudeAgentOptions, HookMatcher,
                              ResultMessage, TextBlock, ToolUseBlock, create_sdk_mcp_server, query,
                              tool)

HERE = Path(__file__).parent.resolve()
APP = HERE / "sample_app"
SESSIONS_FILE = HERE / ".lab3_sessions.json"
SUBAGENT_TOOL = ["Agent", "Task"]          # see NOTE above

BEDROCK_ENV = {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
}
if os.environ.get("ANTHROPIC_MODEL"):
    BEDROCK_ENV["ANTHROPIC_MODEL"] = os.environ["ANTHROPIC_MODEL"]


# ===========================================================================
# PART A — Customer support, the SDK way
# ===========================================================================
CUSTOMERS = {"asha@example.com": {"cust_id": "C-1001", "verified": True, "created": 1688169600}}
ORDERS = {"O-501": {"customer": "C-1001", "amount": 129.0, "status": 3,
                    "placed_at": "2026-09-28T10:15:00+05:30"},
          "O-502": {"customer": "C-1001", "amount": 899.0, "status": 4,
                    "placed_at": "2026-10-02T18:40:00+05:30"}}
STATE = {"verified_customer_id": None}     # hooks are in-process, so they can share state
STATUS = {1: "pending", 2: "shipped", 3: "delivered", 4: "delivered_damaged"}


def _txt(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


@tool("get_customer", "Look up and verify a customer by email.", {"email": str})
async def get_customer(args):
    return _txt(CUSTOMERS.get(args["email"].lower(), {"error": "not_found"}))


@tool("lookup_order", "Get an order by ID (e.g. O-501).", {"order_id": str})
async def lookup_order(args):
    o = ORDERS.get(args["order_id"])
    return _txt({"order_id": args["order_id"], **o} if o else {"error": "not_found"})


@tool("process_refund", "Refund an order to a verified customer.",
      {"customer_id": str, "order_id": str, "amount": float, "reason": str})
async def process_refund(args):
    return _txt({"status": "refund_issued", "refund_id": "R-9001", **args})


@tool("escalate_to_human", "Hand off to a human who cannot see this chat. Provide customer_id, "
      "root_cause, refund_amount, recommended_action.",
      {"customer_id": str, "root_cause": str, "refund_amount": float, "recommended_action": str})
async def escalate_to_human(args):
    print("\n  >>> HANDOFF RECEIVED BY HUMAN QUEUE:\n" + json.dumps(args, indent=4))
    return _txt({"status": "escalated", "ticket": "ESC-301"})


support_server = create_sdk_mcp_server(
    name="support", version="1.0.0",
    tools=[get_customer, lookup_order, process_refund, escalate_to_human])
T = lambda n: f"mcp__support__{n}"          # MCP tool names: mcp__<server>__<tool>


def _deny(input_data, reason):
    return {"hookSpecificOutput": {"hookEventName": input_data["hook_event_name"],
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


async def gate_and_policy(input_data, tool_use_id, context):
    """PreToolUse: deterministic enforcement (1.4 prerequisite gate + 1.5 policy)."""
    name, args = input_data["tool_name"], input_data["tool_input"]
    who = input_data.get("agent_type") or "main"
    if name in (T("lookup_order"), T("process_refund")) and not STATE["verified_customer_id"]:
        print(f"  [PreToolUse] DENY {name} ({who}): customer not verified")
        return _deny(input_data, "Call get_customer and verify the customer first.")
    if name == T("process_refund") and float(args.get("amount", 0)) > 500:
        print(f"  [PreToolUse] DENY refund ${args['amount']}: over $500 limit")
        return _deny(input_data, "Refunds over $500 require a human. Do not retry; call "
                                 "escalate_to_human with customer_id, root_cause, refund_amount "
                                 "and recommended_action.")
    print(f"  [PreToolUse] allow {name} ({who})")
    return {}


def _find_json(resp):
    """tool_response shape varies by tool type; dig out the JSON text we returned."""
    if isinstance(resp, str):
        try:
            return json.loads(resp)
        except ValueError:
            return None
    if isinstance(resp, dict):
        if "text" in resp:
            return _find_json(resp["text"])
        resp = resp.get("content", [])
    if isinstance(resp, list):
        for item in resp:
            found = _find_json(item)
            if found is not None:
                return found
    return None


async def normalize_results(input_data, tool_use_id, context):
    """PostToolUse: normalize heterogeneous formats before Claude reads them (1.5).
    Also opens the verification gate deterministically."""
    data = _find_json(input_data.get("tool_response"))
    if not isinstance(data, dict):
        return {}
    name = input_data["tool_name"]
    if name == T("get_customer") and data.get("verified"):
        STATE["verified_customer_id"] = data["cust_id"]
    if "created" in data and isinstance(data["created"], int):
        data["created"] = datetime.fromtimestamp(data["created"], tz=timezone.utc).isoformat()
    if isinstance(data.get("status"), int):
        data["status"] = STATUS.get(data["status"], "unknown")
    if "placed_at" in data:
        data["placed_at"] = datetime.fromisoformat(data["placed_at"]).astimezone(timezone.utc).isoformat()
    print(f"  [PostToolUse] normalized {name}: {json.dumps(data)[:90]}")
    # updatedToolOutput replaces the result Claude sees. On older SDK/CLI versions use
    # "updatedMCPToolOutput" (MCP tools only) or fall back to "additionalContext".
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "updatedToolOutput": [{"type": "text", "text": json.dumps(data)}]}}


async def track_subagents(input_data, tool_use_id, context):
    print(f"  [{input_data['hook_event_name']}] {input_data.get('agent_type', '')}")
    return {}


async def part_a_support():
    options = ClaudeAgentOptions(
        env=BEDROCK_ENV,
        system_prompt="You are the support coordinator. Verify the customer yourself, then delegate "
                      "order investigation to the order-investigator subagent. It has no access to "
                      "this conversation, so give it the customer ID and order IDs in its prompt. "
                      "Then decide on refunds.",
        mcp_servers={"support": support_server},
        # The coordinator must be allowed the subagent tool or it cannot delegate (1.3)
        allowed_tools=SUBAGENT_TOOL + [T("get_customer"), T("process_refund"), T("escalate_to_human")],
        agents={
            "order-investigator": AgentDefinition(
                description="Investigates specific orders: status, amount, timestamps. Needs the "
                            "verified customer ID and order IDs in its prompt.",
                prompt="You investigate orders with lookup_order and report status, amount and "
                       "whether the item arrived damaged. Report facts only; do not refund.",
                tools=[T("lookup_order")],          # tool restriction for this subagent
            ),
        },
        hooks={
            "PreToolUse": [HookMatcher(matcher="^mcp__support__", hooks=[gate_and_policy])],
            "PostToolUse": [HookMatcher(matcher="^mcp__support__", hooks=[normalize_results])],
            "SubagentStart": [HookMatcher(hooks=[track_subagents])],
            "SubagentStop": [HookMatcher(hooks=[track_subagents])],
        },
        max_turns=30,
    )
    prompt = ("I'm asha@example.com. Headphones from O-501 have a dead ear and the monitor from "
              "O-502 arrived cracked. Please refund both.")
    print(f"USER: {prompt}\n")
    async for msg in query(prompt=prompt, options=options):
        _print(msg)


# ===========================================================================
# PART B — Sessions: named resume, change notification, fork, fresh-with-summary
# ===========================================================================
SAMPLE = {
    "auth.py": "from tokens import make_token\n\ndef login(db, user, pw):\n"
               "    row = db.query(f\"SELECT * FROM users WHERE name='{user}'\")\n"
               "    if row and row.pw == pw:\n        return make_token(user)\n",
    "tokens.py": "import time\n\ndef make_token(user):\n    return f\"{user}:{int(time.time())}\"\n\n"
                 "def check_token(tok):\n    user, ts = tok.split(':')\n    return True\n",
    "api.py": "from tokens import check_token\n\ndef get_orders(db, tok, user_id):\n"
              "    if check_token(tok):\n        return db.orders(user_id)\n",
}
CHANGED_TOKENS = ("import hmac, hashlib, time\nSECRET = b'dev-secret'\n\n"
                  "def make_token(user):\n    ts = str(int(time.time()))\n"
                  "    sig = hmac.new(SECRET, f'{user}:{ts}'.encode(), hashlib.sha256).hexdigest()\n"
                  "    return f'{user}:{ts}:{sig}'\n\n"
                  "def check_token(tok, max_age=3600):\n    user, ts, sig = tok.split(':')\n"
                  "    good = hmac.new(SECRET, f'{user}:{ts}'.encode(), hashlib.sha256).hexdigest()\n"
                  "    return hmac.compare_digest(sig, good) and time.time() - int(ts) < max_age\n")

READ_ONLY = ["Read", "Glob", "Grep"]


def _load():
    return json.loads(SESSIONS_FILE.read_text()) if SESSIONS_FILE.exists() else {}


def _save(name, sid):
    d = _load()
    d[name] = sid
    SESSIONS_FILE.write_text(json.dumps(d, indent=2))
    print(f"\n  saved session name '{name}' -> {sid}")


def _print(msg):
    if isinstance(msg, AssistantMessage):
        for b in msg.content:
            if isinstance(b, TextBlock) and b.text.strip():
                print(f"CLAUDE: {b.text.strip()}\n")
            elif isinstance(b, ToolUseBlock):
                print(f"  -> {b.name}({json.dumps(b.input)[:80]})")
    elif isinstance(msg, ResultMessage):
        cost = f"${msg.total_cost_usd:.4f}" if msg.total_cost_usd else "n/a"
        print(f"[result: {msg.subtype}, turns={msg.num_turns}, cost={cost}, session={msg.session_id}]")


async def _run(prompt, **opts):
    """Run one query, print it, return (session_id, final_text)."""
    sid, final = None, ""
    opts.setdefault("allowed_tools", READ_ONLY)
    options = ClaudeAgentOptions(env=BEDROCK_ENV, cwd=str(APP), max_turns=25, **opts)
    async for msg in query(prompt=prompt, options=options):
        _print(msg)
        if isinstance(msg, ResultMessage):
            sid, final = msg.session_id, (msg.result or "")
    return sid, final


async def b1_analyze():
    APP.mkdir(exist_ok=True)
    for f, src in SAMPLE.items():
        (APP / f).write_text(src)
    sid, final = await _run(
        "This is a legacy codebase with no tests. Map its structure, identify the highest-risk "
        "areas, and propose a prioritized testing plan. End with a JSON block named SUMMARY "
        "containing: files_analyzed, key_risks, test_plan (ordered list).")
    _save("testing-investigation", sid)
    (HERE / ".lab3_summary.txt").write_text(final)
    print("\nCLI equivalent: name a session with /rename testing-investigation, "
          "then continue it later with:  claude --resume testing-investigation")


def b2_change():
    if not APP.exists():
        sys.exit("Run 'python lab3_agent_sdk.py analyze' first.")
    (APP / "tokens.py").write_text(CHANGED_TOKENS)
    print("tokens.py rewritten: tokens are now HMAC-signed with a max_age check.\n"
          "The 'testing-investigation' session still holds the OLD file contents in its history.")


async def b3_resume():
    sid = _load()["testing-investigation"]
    # Tell the agent exactly what changed -> targeted re-analysis, not full re-exploration
    await _run(
        "Since your analysis, tokens.py was modified: tokens are now HMAC-signed and check_token "
        "verifies the signature and a max_age. The other files are unchanged. Re-read ONLY tokens.py, "
        "then tell me which of your earlier risks and test-plan items change.",
        resume=sid)


async def b4_fork():
    base = _load()["testing-investigation"]
    branches = {
        "fork-unit-first": "Take a unit-test-first strategy: write the pytest test list for each "
                           "function in isolation with mocks. Do not write files, just the plan.",
        "fork-integration-first": "Take an integration-first strategy: design end-to-end tests "
                                  "through api.get_orders with a fake db. Do not write files.",
    }
    for name, prompt in branches.items():
        print(f"\n--- branch: {name} ---")
        sid, _ = await _run(prompt, resume=base, fork_session=True)
        _save(name, sid)
        assert sid != base, "a fork must get its own session id"
    print(f"\nBaseline '{base}' is unchanged; resume any of the three independently.")


async def b5_fresh():
    summary = (HERE / ".lab3_summary.txt").read_text() if (HERE / ".lab3_summary.txt").exists() else ""
    sid, _ = await _run(
        "You are continuing a test-planning investigation. Prior findings (may be partly outdated):\n"
        f"{summary[-3000:]}\n\nKnown change since then: tokens.py now uses HMAC-signed tokens with "
        "max_age. Verify against the current files and produce the updated prioritized test plan.")
    _save("testing-fresh", sid)
    print("\nWhy: when many earlier tool results are stale, a fresh session with a structured "
          "summary avoids the model reasoning from outdated file contents.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    actions = {"support": part_a_support, "analyze": b1_analyze, "resume": b3_resume,
               "fork": b4_fork, "fresh": b5_fresh}
    if cmd in actions:
        asyncio.run(actions[cmd]())
    elif cmd == "change":
        b2_change()
    elif cmd == "sessions":
        print(json.dumps(_load(), indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
