"""tool_choice demo: force extract_metadata FIRST, then let the model continue.

  python3 tool_choice_demo.py --choice forced --show-request          offline mock, no key needed
  python3 tool_choice_demo.py --choice any
  python3 tool_choice_demo.py --choice auto
  python3 tool_choice_demo.py --choice forced --force-every-turn      the mistake: force on every turn
  ANTHROPIC_API_KEY=... python3 tool_choice_demo.py --choice forced --backend api --model claude-haiku-5-5

--backend mock  (default) is a tiny stand-in for the Messages API. NO model is involved: it only follows the
                documented rules of each tool_choice option so you can see the request/response flow.
--backend api   sends the real request to https://api.anthropic.com/v1/messages (needs an API key with credits).
"""
import argparse, json, os, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
MAX_TURNS = 5
USER_REQUEST = "Tell me about docs/CONCEPTS.md"
SYSTEM = "You are a TaskFlow documentation assistant. Use the tools to enrich your answer."

TOOLS = [
    {"name": "extract_metadata", "description": "Extract metadata (title, number of lines) from one repository document. Must run before any enrichment tool.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "count_headings", "description": "Enrichment: count the headings in one repository document.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "find_related_tasks", "description": "Enrichment: find task titles that contain a keyword.",
     "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
]
TASK_TITLES = ["Fix invoice PDF export", "Rotate webhook signing secret", "Migrate invoice archive",
               "Audit logs for PII", "Add rate limit to bulk-notify", "Invoice reminder email copy"]


def run_tool(name, args):
    if name in ("extract_metadata", "count_headings"):
        lines = open(os.path.join(REPO, args["path"])).read().splitlines()
        if name == "count_headings":
            return {"headings": sum(l.startswith("#") for l in lines)}
        return {"title": next((l.lstrip("# ") for l in lines if l.startswith("#")), ""), "lines": len(lines)}
    if name == "find_related_tasks":
        return {"tasks": [t for t in TASK_TITLES if args["keyword"].lower() in t.lower()]}
    return {"error": f"unknown tool {name}"}


def choice_for(mode):
    return {"auto": {"type": "auto"}, "any": {"type": "any"},
            "forced": {"type": "tool", "name": "extract_metadata"}}[mode]


# ---------------------------------------------------------------- backends
def mock_model(messages, tool_choice):
    """Follows the documented rules only. No model. auto = model's choice, any = must call a tool, tool = that tool."""
    used = [b["name"] for m in messages if m["role"] == "assistant" for b in m["content"] if b["type"] == "tool_use"]
    use = lambda name, inp: {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": f"toolu_mock{len(used)}", "name": name, "input": inp}]}
    inputs = {"extract_metadata": {"path": "docs/CONCEPTS.md"}, "count_headings": {"path": "docs/CONCEPTS.md"},
              "find_related_tasks": {"keyword": "webhook"}}
    kind = tool_choice["type"]
    if kind == "tool":                                   # forced: always exactly this tool, no text before it
        return use(tool_choice["name"], inputs[tool_choice["name"]])
    if kind == "any":                                    # must call SOME tool. Mock picks the last one listed.
        return use(TOOLS[-1]["name"], inputs[TOOLS[-1]["name"]])
    unused = [t["name"] for t in TOOLS if t["name"] not in used]   # auto
    if not used:                                         # auto may skip tools entirely (the mock chooses to)
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "(mock) docs/CONCEPTS.md is a primer on the concepts behind the labs."}]}
    if unused:
        return use(unused[0], inputs[unused[0]])
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": f"(mock) Final answer, built from: {', '.join(used)}."}]}


def api_model(model):
    def call(messages, tool_choice):
        body = request_body(model, messages, tool_choice)
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01",
                                              "content-type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as err:
            sys.exit(f"API error {err.code}: {err.read().decode()[:400]}")
    return call


def request_body(model, messages, tool_choice):
    return {"model": model, "max_tokens": 1024, "system": SYSTEM, "tools": TOOLS, "tool_choice": tool_choice, "messages": messages}


# ---------------------------------------------------------------- the flow
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--choice", choices=["auto", "any", "forced"], required=True)
    p.add_argument("--backend", choices=["mock", "api"], default="mock")
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--force-every-turn", action="store_true", help="keep the same tool_choice on every turn (a mistake)")
    p.add_argument("--show-request", action="store_true", help="print the JSON request body of every turn")
    a = p.parse_args()
    if a.backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("--backend api needs ANTHROPIC_API_KEY (an API key with credits). Use --backend mock to run offline.")
    call = mock_model if a.backend == "mock" else api_model(a.model)

    messages = [{"role": "user", "content": USER_REQUEST}]
    called = []
    for turn in range(1, MAX_TURNS + 1):
        choice = choice_for(a.choice) if (turn == 1 or a.force_every_turn) else {"type": "auto"}   # force only the first turn
        if a.show_request:
            print(f"--- request, turn {turn}\n{json.dumps(request_body(a.model, messages, choice), indent=2)}")
        response = call(messages, choice)
        blocks = response["content"]
        kinds = ", ".join(f"{b['type']}:{b.get('name', '')}".rstrip(":") for b in blocks)
        print(f"TURN {turn}  tool_choice={json.dumps(choice)}\n        model returned -> {kinds}")
        messages.append({"role": "assistant", "content": blocks})
        tool_uses = [b for b in blocks if b["type"] == "tool_use"]
        if not tool_uses:
            print("        text:", "".join(b.get("text", "") for b in blocks)[:300])
            break
        results = []
        for b in tool_uses:
            called.append(b["name"])
            out = run_tool(b["name"], b["input"])
            print(f"        ran {b['name']}({json.dumps(b['input'])}) -> {json.dumps(out)}")
            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})
    else:
        print(f"STOPPED after {MAX_TURNS} turns: with the same forced tool_choice on every turn the model can never finish.")

    print(f"\nTOOLS CALLED, IN ORDER: {called or 'none'}")
    print("CHECK first call was extract_metadata:", "YES" if called[:1] == ["extract_metadata"] else "NO")
    print("CHECK at least one tool was called:   ", "YES" if called else "NO")


main()
