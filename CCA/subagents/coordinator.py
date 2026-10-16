"""Hub-and-spoke coordinator: spawns subagents through a Task tool."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from agents import AGENTS, run_subagent
from bedrock import call_claude

TASK_TOOL = {
    "name": "Task",
    "description": "Spawn a subagent. It starts with NO knowledge of this conversation, so the prompt must "
                   "contain everything it needs (scope, prior findings, output needs). Available subagents:\n"
                   + "\n".join(f"- {k}: {v.description}" for k, v in AGENTS.items()),
    "input_schema": {"type": "object", "properties": {
        "subagent_type": {"type": "string", "enum": list(AGENTS)},
        "prompt": {"type": "string"}}, "required": ["subagent_type", "prompt"]},
}

COORDINATOR_SYSTEM = """You coordinate a research team via the Task tool.
Goal: answer the user's question accurately, with every claim attributed to a source.
Quality bar:
- Breadth: a broad question needs several distinct angles. Do not narrow it to one sub-topic.
- No duplication: give each researcher a distinct sub-topic or source type.
- Proportionate effort: a narrow factual question may need just one researcher. Don't run the whole team by default.
- Parallelism: launch independent research tasks together in ONE response.
- Synthesis: the synthesizer has no tools and no memory, so pass it every finding verbatim, as JSON with sources.
- If synthesis reports important coverage gaps, run targeted follow-up research and synthesize again
  (at most 2 refinement rounds).
When done, reply with the final answer (no tool call)."""


def dispatch(call):
    """Run one subagent. Errors are caught HERE, at the hub, and returned in one consistent shape."""
    try:
        out = run_subagent(call["input"]["subagent_type"], call["input"]["prompt"])
        return {"type": "tool_result", "tool_use_id": call["id"], "content": out}
    except Exception as e:
        return {"type": "tool_result", "tool_use_id": call["id"], "is_error": True,
                "content": json.dumps({"error": type(e).__name__, "detail": str(e)[:300],
                                       "subagent": call["input"]["subagent_type"]})}


def coordinator(question):
    messages = [{"role": "user", "content": question}]
    total, rounds = 0, 0
    while True:
        resp = call_claude(COORDINATOR_SYSTEM, messages, tools=[TASK_TOOL], max_tokens=4000)
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp["stop_reason"] == "end_turn":
            print(f"[coordinator] done: {rounds} round(s), {total} subagent(s) spawned")
            return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()
        calls = [b for b in resp["content"] if b["type"] == "tool_use"]
        rounds += 1
        total += len(calls)
        print(f"[coordinator] round {rounds}: spawning {len(calls)} in parallel -> "
              f"{[c['input']['subagent_type'] for c in calls]}")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(dispatch, calls))
        for r in results:
            flag = "ERROR " if r.get("is_error") else ""
            print(f"[hub<-spoke] {flag}{r['content'][:120]!r}")
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print("\n" + coordinator(sys.argv[1]))
