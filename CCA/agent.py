"""support agent: a model-driven agentic loop with pluggable hooks."""
import argparse
import json

from bedrock import call_claude
from tools import ESCALATIONS, REFUNDS_ISSUED, TOOLS, run_tool

SYSTEM = """You are a customer-support agent for an electronics retailer.
Resolve the customer's request using the tools. Verify the customer with get_customer before
acting on their account. If a request contains several issues, handle each one and give a
single combined answer at the end. When you escalate, write a handoff a human can act on
without reading this chat. Keep the final reply short and friendly."""

SAFETY_CAP = 25   # runaway backstop only -- NOT how the loop is supposed to end


def run_agent(user_message, pre_hooks=(), post_hooks=()):
    state = {"verified_customer_id": None}          # facts the HARNESS knows for certain
    messages = [{"role": "user", "content": user_message}]

    for turn in range(1, SAFETY_CAP + 1):
        resp = call_claude(SYSTEM, messages, tools=TOOLS)
        stop = resp["stop_reason"]
        print(f"[turn {turn}] stop_reason={stop}")

        # 1. Always append the FULL assistant content (text + tool_use blocks)
        messages.append({"role": "assistant", "content": resp["content"]})

        # 2. The only normal exit
        if stop == "end_turn":
            return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()
        if stop != "tool_use":
            raise RuntimeError(f"Unexpected stop_reason: {stop}")

        # 3. Execute every tool Claude asked for
        calls = [b for b in resp["content"] if b["type"] == "tool_use"]
        if len(calls) > 1:
            print(f"  [parallel] {len(calls)} tool calls in one response: {[c['name'] for c in calls]}")
        results = []
        for call in calls:
            name, args = call["name"], call["input"]
            blocked = None
            for hook in pre_hooks:                    # PreToolUse-style hooks
                blocked = hook(name, args, state)
                if blocked:
                    break
            if blocked:
                print(f"  [PRE-HOOK BLOCKED] {name}: {blocked['error']}")
                out = blocked
            else:
                out = run_tool(name, args)
                for hook in post_hooks:               # PostToolUse-style hooks
                    out = hook(name, out, state)
                print(f"  [tool] {name}({json.dumps(args)}) -> {json.dumps(out)[:160]}")
            results.append({"type": "tool_result", "tool_use_id": call["id"],
                            "content": json.dumps(out), "is_error": "error" in out})

        # 4. All results go back in ONE user message so Claude can reason over them
        messages.append({"role": "user", "content": results})

    raise RuntimeError("Safety cap reached -- a backstop, not the stopping mechanism")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message", help="what the customer says")
    ap.add_argument("--hooks", default="", help="comma-separated hook groups from hooks.py")
    a = ap.parse_args()

    pre, post = [], []
    if a.hooks:
        from hooks import load_hooks
        pre, post = load_hooks(a.hooks.split(","))
        print(f"hooks enabled: {a.hooks}")
    else:
        print("hooks enabled: NONE")

    answer = run_agent(a.message, pre, post)
    print(f"\nAGENT: {answer}\n")
    print("REFUNDS_ISSUED:", json.dumps(REFUNDS_ISSUED))
    print("ESCALATIONS:", json.dumps(ESCALATIONS, indent=2))


if __name__ == "__main__":
    main()
