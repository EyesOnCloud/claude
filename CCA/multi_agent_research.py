"""
LAB 2 — Coordinator/subagent research system + task decomposition patterns
Covers CCA-F Task Statements 1.2, 1.3, 1.6   (raw boto3 / Bedrock InvokeModel)

Run:
    python lab2_multi_agent_research.py research            # Part A: hub-and-spoke research
    python lab2_multi_agent_research.py research --simple   # coordinator should pick FEWER agents
    python lab2_multi_agent_research.py review              # Part B: prompt-chained code review
    python lab2_multi_agent_research.py adaptive            # Part C: adaptive decomposition

Part A builds by hand what the Agent SDK gives you as AgentDefinition + the Task tool,
so you can see every moving part:
  - AgentDefinition: description + system prompt + restricted tools per subagent      (1.3)
  - a "Task" tool the coordinator calls to spawn subagents                             (1.3)
  - each subagent starts with an EMPTY history: it only knows what the prompt says     (1.2/1.3)
  - several Task calls in ONE coordinator response run in parallel                     (1.3)
  - all results return to the coordinator (hub-and-spoke), errors are normalized there (1.2)
  - findings travel as structured JSON with source metadata to preserve attribution    (1.3)
  - the coordinator checks synthesis for gaps and re-delegates (iterative refinement) (1.2)
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from common import banner, call_claude, extract_json, log, text_of, tool_uses

# ---------------------------------------------------------------------------
# A tiny offline corpus so the lab is deterministic and needs no web access.
# Two "source types": web articles and internal PDF reports (with page numbers).
# ---------------------------------------------------------------------------
WEB = [
    {"url": "https://example.org/ai-music-2026", "title": "AI tools reshape music production",
     "text": "Survey of 1,200 producers: 64% use AI for mastering or stem separation. Session "
             "musician bookings fell 18% year on year in pop and advertising work."},
    {"url": "https://example.org/visual-artists-licensing", "title": "Illustrators push for licensing deals",
     "text": "Several stock-image platforms now pay contributors when their images are used to "
             "train models. Payouts averaged under $40 per artist in the first year."},
    {"url": "https://example.org/film-vfx-jobs", "title": "VFX studios automate rotoscoping",
     "text": "Large VFX houses report rotoscoping and cleanup time down 50-70%. Entry-level "
             "roles shrank while demand for pipeline TDs grew."},
    {"url": "https://example.org/writers-guild", "title": "Writers' contracts add AI clauses",
     "text": "New screenwriting contracts bar studios from crediting AI as a writer and require "
             "disclosure when AI-generated material is handed to writers."},
]
REPORTS = [
    {"doc": "Creative-Economy-Outlook-2026.pdf", "page": 12,
     "text": "Total creative-sector employment rose 2.1% despite automation, driven by game "
             "development and independent content creation."},
    {"doc": "Creative-Economy-Outlook-2026.pdf", "page": 31,
     "text": "Copyright litigation over training data: 40+ active cases; outcomes will set "
             "licensing norms for visual art and music."},
    {"doc": "Skills-Gap-Survey.pdf", "page": 4,
     "text": "Employers rank 'AI-assisted workflow skills' as the top hiring gap for "
             "junior creative roles in 2026."},
]


def web_search(query):
    q = set(query.lower().split())
    hits = [d for d in WEB if q & set((d["title"] + " " + d["text"]).lower().split())]
    return hits or [{"note": "no results", "query": query}]


def search_reports(query):
    q = set(query.lower().split())
    hits = [d for d in REPORTS if q & set(d["text"].lower().split())]
    return hits or [{"note": "no results", "query": query}]


SUBAGENT_TOOL_IMPLS = {"web_search": web_search, "search_reports": search_reports}
SUBAGENT_TOOL_SCHEMAS = {
    "web_search": {"name": "web_search", "description": "Search web articles. Returns url, title, text.",
                   "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                                    "required": ["query"]}},
    "search_reports": {"name": "search_reports",
                       "description": "Search internal PDF reports. Returns doc, page, text.",
                       "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                                        "required": ["query"]}},
}

FINDINGS_FORMAT = """Return ONLY JSON: {"findings": [{"claim": str, "evidence": str,
"source": {"type": "web"|"report", "url": str|null, "doc": str|null, "page": int|null}}],
"gaps": [str]}"""


# ---------------------------------------------------------------------------
# AgentDefinition — mirrors the Agent SDK's shape: description, prompt, tools
# ---------------------------------------------------------------------------
@dataclass
class AgentDefinition:
    description: str          # what the COORDINATOR reads to decide whether to use it
    prompt: str               # the subagent's own system prompt
    tools: list = field(default_factory=list)   # tool restriction


AGENTS = {
    "web_researcher": AgentDefinition(
        description="Finds evidence in web articles. Give it a specific sub-topic.",
        prompt="You research ONE assigned sub-topic using web_search only. Search 1-3 times, "
               "then report. Every finding must carry its URL. " + FINDINGS_FORMAT,
        tools=["web_search"]),
    "report_analyst": AgentDefinition(
        description="Extracts evidence from internal PDF reports (cites doc + page).",
        prompt="You analyse internal reports using search_reports only. Every finding must "
               "carry doc and page. " + FINDINGS_FORMAT,
        tools=["search_reports"]),
    "synthesizer": AgentDefinition(
        description="Writes the final cited answer from findings you pass it. Has NO search tools, "
                    "so include ALL findings (with sources) in its prompt.",
        prompt="Write a concise, well-organised answer using ONLY the findings in the prompt. "
               "Cite each claim inline as [url] or [doc p.N]. Then output a line 'COVERAGE_GAPS:' "
               "followed by a JSON list of important aspects of the question the findings do not "
               "cover (empty list if none).",
        tools=[]),
}


def run_subagent(agent_type, prompt):
    """Spawn a subagent with ISOLATED context: a brand-new message list.
    It cannot see the coordinator's history -- only `prompt`."""
    d = AGENTS[agent_type]
    tools = [SUBAGENT_TOOL_SCHEMAS[t] for t in d.tools]
    messages = [{"role": "user", "content": prompt}]
    while True:
        resp = call_claude(d.prompt, messages, tools=tools or None, max_tokens=3000)
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp["stop_reason"] != "tool_use":
            return text_of(resp["content"])
        results = []
        for c in tool_uses(resp["content"]):
            if c["name"] not in d.tools:   # enforce the tool restriction in code
                out = {"error": f"{agent_type} is not allowed to use {c['name']}"}
            else:
                out = SUBAGENT_TOOL_IMPLS[c["name"]](**c["input"])
            log(f"  {agent_type[:12]}", f"{c['name']}({c['input']}) -> {len(out)} hit(s)")
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})


# The coordinator's ONLY way to reach subagents (hub-and-spoke)
TASK_TOOL = {
    "name": "Task",
    "description": "Spawn a subagent. It starts with NO knowledge of this conversation, so the "
                   "prompt must contain everything it needs (scope, prior findings, output needs).\n"
                   + "\n".join(f"- {k}: {v.description}" for k, v in AGENTS.items()),
    "input_schema": {"type": "object", "properties": {
        "subagent_type": {"type": "string", "enum": list(AGENTS)},
        "prompt": {"type": "string"}},
        "required": ["subagent_type", "prompt"]},
}

# Goals + quality criteria, NOT a step-by-step procedure (1.3)
COORDINATOR_SYSTEM = """You coordinate a research team via the Task tool.

Goal: answer the user's question accurately, with every claim attributed to a source.
Quality bar:
- Breadth: a broad question needs several distinct angles. Do not narrow it to one sub-topic.
- No duplication: give each researcher a distinct sub-topic or source type.
- Proportionate effort: a narrow factual question may need just one researcher; don't run the
  whole team by default.
- Parallelism: launch independent research tasks together in ONE response.
- Synthesis: the synthesizer has no tools and no memory, so pass it every finding verbatim,
  as JSON with sources.
- If synthesis reports important coverage gaps, run targeted follow-up research and synthesize
  again (at most 2 refinement rounds).
When done, reply with the final answer (no tool call)."""


def coordinator(question):
    messages = [{"role": "user", "content": question}]
    spawned = 0
    while True:
        resp = call_claude(COORDINATOR_SYSTEM, messages, tools=[TASK_TOOL], max_tokens=4000)
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp["stop_reason"] == "end_turn":
            log("coordinator", f"done after spawning {spawned} subagents")
            return text_of(resp["content"])

        calls = tool_uses(resp["content"])
        log("coordinator", f"spawning {len(calls)} subagent(s) in parallel: "
                           f"{[c['input']['subagent_type'] for c in calls]}")
        spawned += len(calls)

        def dispatch(c):
            try:
                out = run_subagent(c["input"]["subagent_type"], c["input"]["prompt"])
                return {"type": "tool_result", "tool_use_id": c["id"], "content": out}
            except Exception as e:     # consistent error handling lives in the hub
                return {"type": "tool_result", "tool_use_id": c["id"], "is_error": True,
                        "content": json.dumps({"error": type(e).__name__, "detail": str(e)[:300],
                                               "subagent": c["input"]["subagent_type"]})}

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(dispatch, calls))
        for r in results:   # observability: every spoke's output passes through here
            log("hub<-spoke", (r["content"] if isinstance(r["content"], str) else "")[:110].replace("\n", " "))
        messages.append({"role": "user", "content": results})


# ---------------------------------------------------------------------------
# PART B (1.6) — Prompt chaining: per-file local passes, then a cross-file pass
# ---------------------------------------------------------------------------
REPO = {
    "auth.py": '''def login(user, pw):
    row = db.query(f"SELECT * FROM users WHERE name='{user}'")
    if row and row.pw == pw:
        return make_token(user)
''',
    "tokens.py": '''import time
def make_token(user):
    return f"{user}:{int(time.time())}"
def check_token(tok):
    user, ts = tok.split(":")
    return True
''',
    "api.py": '''from auth import login
from tokens import check_token
def get_orders(tok, user_id):
    if check_token(tok):
        return db.orders(user_id)
''',
}


def chained_review():
    local = {}
    for path, src in REPO.items():              # step 1..N: one focused pass per file
        out = call_claude(
            "You review ONE file. List concrete bugs and security issues with line references. "
            "Also list what this file exports and what it assumes about other modules.",
            [{"role": "user", "content": f"File: {path}\n```python\n{src}```"}], max_tokens=800)
        local[path] = text_of(out["content"])
        log("local pass", f"{path}: {local[path][:90]!r}")
    summary = "\n\n".join(f"### {p}\n{r}" for p, r in local.items())
    out = call_claude(                           # final step: integration pass
        "You do the CROSS-FILE integration review. Using the per-file notes, find issues that only "
        "appear when files interact (broken contracts, trust assumptions, auth flows).",
        [{"role": "user", "content": summary}], max_tokens=1200)
    return text_of(out["content"])


# ---------------------------------------------------------------------------
# PART C (1.6) — Adaptive decomposition: plan, act, re-plan from what was found
# ---------------------------------------------------------------------------
def adaptive_test_plan():
    goal = "Add comprehensive tests to this legacy codebase."
    plan = extract_json(text_of(call_claude(
        "Map the codebase, then produce a prioritized test plan. Return ONLY JSON: "
        '{"structure": str, "high_impact": [str], "tasks": [{"id": int, "task": str, "priority": int}]}',
        [{"role": "user", "content": goal + "\n\n" + json.dumps(REPO)}], max_tokens=1200)["content"]))
    log("plan v1", json.dumps(plan["tasks"])[:200])
    # Simulate discovering something while executing task 1
    discovery = ("While writing tests for tokens.check_token we found it never validates the "
                 "timestamp or signature, and api.get_orders never checks user_id matches the token.")
    plan2 = extract_json(text_of(call_claude(
        "Revise the test plan given a new discovery. Re-prioritize, add or drop tasks. Return the "
        'same JSON shape plus "changes": [str].',
        [{"role": "user", "content": json.dumps(plan) + "\n\nDiscovery: " + discovery}],
        max_tokens=1200)["content"]))
    return plan, plan2


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "research"
    if mode == "research":
        q = ("What is the impact of AI on employment in the creative industries?"
             if "--simple" not in sys.argv else
             "According to our internal reports, how many copyright cases over training data are active?")
        banner(f"PART A — Coordinator: {q}")
        print(coordinator(q))
    elif mode == "review":
        banner("PART B — Prompt chaining: per-file passes + cross-file integration pass")
        print(chained_review())
    elif mode == "adaptive":
        banner("PART C — Adaptive decomposition")
        v1, v2 = adaptive_test_plan()
        print("PLAN v1:", json.dumps(v1, indent=2))
        print("\nPLAN v2 (after discovery):", json.dumps(v2, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
