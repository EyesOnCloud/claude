"""Subagent definitions and the function that runs one subagent in an isolated context."""
import json
import sys
from dataclasses import dataclass, field

from bedrock import call_claude
from corpus import TOOL_IMPLS, TOOL_SCHEMAS

FINDINGS_FORMAT = ('Return ONLY JSON: {"findings": [{"claim": str, "evidence": str, '
                   '"source": {"type": "web"|"report", "url": str|null, "doc": str|null, "page": int|null}}], '
                   '"gaps": [str]}')


@dataclass
class AgentDefinition:
    description: str                              # read by the COORDINATOR to decide whether to use it
    prompt: str                                   # the subagent's own system prompt
    tools: list = field(default_factory=list)     # tool restriction


AGENTS = {
    "web_researcher": AgentDefinition(
        description="Finds evidence in web articles. Give it one specific sub-topic.",
        prompt="You research ONE assigned sub-topic using web_search only. Search 1-3 times, then report. "
               "Every finding must carry its URL. " + FINDINGS_FORMAT,
        tools=["web_search"]),
    "report_analyst": AgentDefinition(
        description="Extracts evidence from internal PDF reports and cites doc + page.",
        prompt="You analyse internal reports using search_reports only. Every finding must carry doc and "
               "page. " + FINDINGS_FORMAT,
        tools=["search_reports"]),
    "synthesizer": AgentDefinition(
        description="Writes the final cited answer from findings you pass it. It has NO tools and NO memory, "
                    "so include ALL findings (with sources) in its prompt.",
        prompt="Write a concise, well-organised answer using ONLY the findings in the prompt. Cite each claim "
               "inline as [url] or [doc p.N]. If no findings are provided, say so. Finish with a line "
               "'COVERAGE_GAPS:' followed by a JSON list of important aspects not covered (empty if none).",
        tools=[]),
}


def run_subagent(agent_type, prompt, log=print):
    """ISOLATED context: the subagent sees only `prompt`, never the caller's history."""
    d = AGENTS[agent_type]
    tools = [TOOL_SCHEMAS[t] for t in d.tools]
    messages = [{"role": "user", "content": prompt}]          # <-- fresh history every time
    while True:
        resp = call_claude(d.prompt, messages, tools=tools or None, max_tokens=3000)
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp["stop_reason"] != "tool_use":
            return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()
        results = []
        for c in (b for b in resp["content"] if b["type"] == "tool_use"):
            if c["name"] not in d.tools:                       # tool restriction enforced in code
                out = {"error": f"{agent_type} is not allowed to use {c['name']}"}
            else:
                out = TOOL_IMPLS[c["name"]](**c["input"])
            log(f"    [{agent_type}] {c['name']}({c['input']}) -> {len(out)} result(s)")
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print(run_subagent(sys.argv[1], sys.argv[2]))
