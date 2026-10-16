"""SDK support agent.  python support_agent.py [--hooks] [--subagent] "message" """
import argparse
import asyncio
import json

from claude_agent_sdk import (AgentDefinition, AssistantMessage, ClaudeAgentOptions, HookMatcher,
                              ResultMessage, TextBlock, ToolUseBlock, query)

import support_tools as st
from config import BEDROCK_ENV

SUBAGENT_TOOL = ["Agent", "Task"]   # exam guide: "Task"; current SDK name: "Agent". Allow both.


def build_options(use_hooks, use_subagent):
    opts = dict(env=BEDROCK_ENV, mcp_servers={"support": st.server}, max_turns=30,
                allowed_tools=list(st.ALL_TOOLS))
    if use_subagent:
        opts["system_prompt"] = ("You are the support coordinator. Verify the customer with get_customer yourself, "
                                 "then delegate ALL order investigation to the order-investigator subagent. It cannot "
                                 "see this conversation, so put the customer ID and order IDs in its prompt. Then "
                                 "decide on refunds or escalation.")
        opts["allowed_tools"] = SUBAGENT_TOOL + st.ALL_TOOLS
        opts["agents"] = {"order-investigator": AgentDefinition(
            description="Investigates specific orders (status, amount, timestamps). Needs the verified customer "
                        "ID and the order IDs in its prompt.",
            prompt="Investigate the given orders with lookup_order and report status, amount and whether the item "
                   "arrived damaged. Facts only; never refund.",
            tools=[st.T("lookup_order")])}
    else:
        opts["system_prompt"] = ("You are a support agent. Verify the customer with get_customer before any account "
                                 "action. Refunds over $500 must be escalated to a human.")
    if use_hooks:
        from sdk_hooks import HOOKS
        opts["hooks"] = HOOKS
    return ClaudeAgentOptions(**opts)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message")
    ap.add_argument("--hooks", action="store_true")
    ap.add_argument("--subagent", action="store_true")
    a = ap.parse_args()
    print(f"hooks={'ON' if a.hooks else 'OFF'}  subagent={'ON' if a.subagent else 'OFF'}\n")
    async for msg in query(prompt=a.message, options=build_options(a.hooks, a.subagent)):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    print(f"  -> {b.name}({json.dumps(b.input)[:100]})")
                elif isinstance(b, TextBlock) and b.text.strip():
                    print(f"CLAUDE: {b.text.strip()}\n")
        elif isinstance(msg, ResultMessage):
            print(f"[result] {msg.subtype}, turns={msg.num_turns}, session={msg.session_id}")
    print("\nREFUNDS:", json.dumps(st.REFUNDS))
    print("HANDOFFS:", json.dumps(st.HANDOFFS, indent=2))


asyncio.run(main())
