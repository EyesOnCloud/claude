"""Run:  python -m pytest -v test_agents.py   (or: python test_agents.py)"""
import agents


def fake_model(responses, seen):
    def _call(system, messages, tools=None, **kw):
        seen.append({"system": system, "messages": [dict(m) for m in messages],
                     "tools": [t["name"] for t in (tools or [])]})
        return responses.pop(0)
    return _call


def test_subagent_starts_with_only_the_prompt():
    seen = []
    agents.call_claude = fake_model([{"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}], seen)
    agents.run_subagent("synthesizer", "ONLY THIS PROMPT", log=lambda *_: None)
    assert seen[0]["messages"] == [{"role": "user", "content": "ONLY THIS PROMPT"}]


def test_subagent_only_receives_its_own_tools():
    seen = []
    agents.call_claude = fake_model([{"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}], seen)
    agents.run_subagent("report_analyst", "x", log=lambda *_: None)
    assert seen[0]["tools"] == ["search_reports"]


def test_forbidden_tool_call_is_refused():
    seen = []
    agents.call_claude = fake_model([
        {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t1", "name": "web_search",
                                                 "input": {"query": "music"}}]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}], seen)
    agents.run_subagent("report_analyst", "x", log=lambda *_: None)
    tool_result = seen[1]["messages"][-1]["content"][0]["content"]
    assert "not allowed" in tool_result


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print(f"PASS {n}")
