"""TaskFlow tools for the tool-interface lab (a tiny MCP server).
The TOOLSET env var picks which tool list Claude sees (toolsets/<TOOLSET>.json)."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
TOOLSET = json.load(open(os.path.join(HERE, "toolsets", os.environ["TOOLSET"] + ".json")))

TASKS = [  # live task records (a stand-in for the database)
    {"id": 1, "title": "Fix invoice PDF export", "status": "open"},
    {"id": 2, "title": "Rotate webhook signing secret", "status": "in_progress"},
    {"id": 3, "title": "Migrate invoice archive", "status": "done"},
    {"id": 4, "title": "Audit logs for PII", "status": "done"},
    {"id": 5, "title": "Add rate limit to bulk-notify", "status": "in_progress"},
    {"id": 6, "title": "Invoice reminder email copy", "status": "open"},
]

def lines_of(path):
    path = path.strip().replace(REPO + "/", "").lstrip("./")   # accept absolute paths too
    if "/" not in path:                      # allow bare names like task_service.py
        for d in ("app", "migrations", "docs"):
            if os.path.isfile(os.path.join(REPO, d, path)):
                path = f"{d}/{path}"
    if not path.startswith(("app/", "migrations/", "docs/", "CLAUDE.md", "README.md")):
        raise ValueError("not a repo file. Task records are not files.")
    return path, open(os.path.join(REPO, path)).read().splitlines()

def search_task_records(status=None, title_contains=None):
    rows = [t for t in TASKS if (not status or t["status"] == status)
            and (not title_contains or title_contains.lower() in t["title"].lower())]
    return {"count": len(rows), "tasks": rows}

def get_task_by_id(task_id):
    return next((t for t in TASKS if t["id"] == int(task_id)), {"error": "no such task"})

def extract_data_points(path, extractor):
    path, ls = lines_of(path)
    if extractor == "markdown_table":
        rows = [[c.strip() for c in l.strip("| ").split("|")] for l in ls if l.startswith("|") and "---" not in l]
        return {"source": path, "rows": rows}
    if extractor == "logger_calls":
        return {"source": path, "rows": [{"line": i, "text": " ".join(x.strip() for x in ls[i - 1:i + 3])}
                                         for i, l in enumerate(ls, 1) if "logger." in l]}
    return {"error": "extractor must be markdown_table or logger_calls"}

def summarize_content(path):
    path, ls = lines_of(path)
    return {"source": path, "outline": [l for l in ls if l.startswith("#") or l.startswith('"""') or l.startswith("def ")][:15],
            "instruction": "Write 3-5 bullet points from this outline."}

def verify_claim_against_source(claim, path):
    path, ls = lines_of(path)
    words = [w.lower() for w in re.findall(r"[A-Za-z_]{4,}", claim)]
    stem = lambda w: w[:-1] if w.endswith("s") else w
    hit = {i for i, l in enumerate(ls, 1) if any(stem(w) in l.lower() for w in words)}
    for i in sorted(hit):                    # a matching def brings its body along
        if ls[i - 1].lstrip().startswith("def "):
            hit |= set(range(i + 1, min(i + 6, len(ls) + 1)))
    return {"source": path, "evidence": [{"line": i, "text": ls[i - 1].rstrip()} for i in sorted(hit)][:25],
            "instruction": "Rule SUPPORTED, CONTRADICTED or NOT_FOUND and cite line numbers."}

# old, vague names (toolsets a0, a1, a2, b0) -> same code underneath
def analyze_content(query): return search_task_records(title_contains=query)
def get_task(id): return get_task_by_id(id)
def analyze_document(path, mode="summarize", claim=""):
    if mode == "verify": return verify_claim_against_source(claim, path)
    if mode == "extract":                                                    # one hidden extractor
        path, ls = lines_of(path)
        return {"source": path, "rows": [{"line": i, "text": l.strip()} for i, l in enumerate(ls, 1) if "DEFECT #" in l]}
    return summarize_content(path)

def reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n"); sys.stdout.flush()

for line in sys.stdin:
    if not line.strip(): continue
    req = json.loads(line); mid = req.get("id"); p = req.get("params") or {}
    if mid is None: continue
    if req["method"] == "initialize":
        reply(mid, {"protocolVersion": p.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                    "serverInfo": {"name": "taskflow", "version": "1"}})
    elif req["method"] == "tools/list":
        reply(mid, {"tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
                              for t in TOOLSET["tools"]]})
    elif req["method"] == "tools/call":
        try: out = globals()[p["name"]](**(p.get("arguments") or {}))
        except Exception as e: out = {"error": str(e)}
        reply(mid, {"content": [{"type": "text", "text": json.dumps(out, indent=1)}], "isError": "error" in out})
    else:
        reply(mid, {})
