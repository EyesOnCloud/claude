"""All TaskFlow tools for the scoped-tools lab (a tiny MCP server).
The TOOLSET env var picks toolsets/<TOOLSET>.json, which decides WHICH of these tools Claude can see.
Web and ops tools are simulated: they never touch the network or run commands."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TOOLSET = json.load(open(os.path.join(HERE, "toolsets", os.environ["TOOLSET"] + ".json")))

TASKS = [
    {"id": 1, "title": "Fix invoice PDF export", "status": "open"},
    {"id": 2, "title": "Rotate webhook signing secret", "status": "in_progress"},
    {"id": 3, "title": "Migrate invoice archive", "status": "done"},
    {"id": 4, "title": "Audit logs for PII", "status": "done"},
    {"id": 5, "title": "Add rate limit to bulk-notify", "status": "in_progress"},
    {"id": 6, "title": "Invoice reminder email copy", "status": "open"},
]
READABLE = ("app/", "migrations/", "docs/", "tests/", "CLAUDE.md", "README.md", "AGENTS.md")


class ToolError(Exception):
    def __init__(self, category, retryable, message, **extra):
        self.body = {"errorCategory": category, "isRetryable": retryable, "message": message, **extra}


def repo_lines(path):
    path = path.strip().replace(REPO + "/", "").lstrip("./")
    if "/" not in path:
        for d in ("app", "migrations", "docs", "tests"):
            if os.path.isfile(os.path.join(REPO, d, path)):
                path = f"{d}/{path}"
    if not path.startswith(READABLE) or not os.path.isfile(os.path.join(REPO, path)):
        raise ToolError("validation", False, f"'{path}' is not a readable repository file")
    return path, open(os.path.join(REPO, path)).read().splitlines()


# ---------------- task records (5) ----------------
def search_task_records(status=None, title_contains=None):
    rows = [t for t in TASKS if (not status or t["status"] == status)
            and (not title_contains or title_contains.lower() in t["title"].lower())]
    return {"count": len(rows), "tasks": rows}

def get_task_by_id(task_id):
    task = next((t for t in TASKS if t["id"] == int(task_id)), None)
    if not task: raise ToolError("validation", False, f"No task with id {task_id}")
    return task

def count_tasks_by_status(status):
    return {"status": status, "count": sum(t["status"] == status for t in TASKS)}

def list_tasks():
    return {"count": len(TASKS), "tasks": TASKS}

def update_task_status(task_id, status):
    task = get_task_by_id(task_id); task["status"] = status
    return {"id": task["id"], "status": status}

# ---------------- repository files (5) ----------------
def read_file(path):
    path, ls = repo_lines(path)
    return {"path": path, "content": "\n".join(ls)[:6000]}

def list_repo_files(directory="."):
    out = []
    for d in ("app", "migrations", "docs", "tests"):
        out += [f"{d}/{f}" for f in sorted(os.listdir(os.path.join(REPO, d))) if f.endswith((".py", ".md"))]
    return {"files": out + ["CLAUDE.md", "README.md"]}

def extract_data_points(path, extractor):
    path, ls = repo_lines(path)
    if extractor == "markdown_table":
        return {"path": path, "rows": [[c.strip() for c in l.strip("| ").split("|")] for l in ls if l.startswith("|") and "---" not in l]}
    if extractor == "logger_calls":
        return {"path": path, "rows": [{"line": i, "text": " ".join(x.strip() for x in ls[i - 1:i + 3])} for i, l in enumerate(ls, 1) if "logger." in l]}
    raise ToolError("validation", False, "extractor must be markdown_table or logger_calls")

def summarize_content(path):
    path, ls = repo_lines(path)
    return {"path": path, "outline": [l for l in ls if l.startswith(("#", '"""', "def "))][:15]}

def verify_claim_against_source(claim, path):
    path, ls = repo_lines(path)
    words = [w.lower().rstrip("s") for w in re.findall(r"[A-Za-z_]{4,}", claim)]
    hits = [i for i, l in enumerate(ls, 1) if any(w in l.lower() for w in words)]
    return {"path": path, "evidence": [{"line": i, "text": ls[i - 1].rstrip()} for i in hits][:20]}

# ---------------- web (3, simulated) ----------------
def web_search(query):
    return {"note": "(simulated)", "results": [{"title": f"Result for '{query}'", "url": "https://example.com/result-1"}]}

def fetch_url(url):
    return {"note": "(simulated)", "url": url, "content": "Simulated page content. In a real run this could be ANY site, including internal ones."}

def check_url_status(url):
    return {"note": "(simulated)", "url": url, "http_status": 200}

# ---------------- ops (5, simulated) ----------------
def run_shell(command):
    return {"note": "(simulated, not executed)", "command": command, "output": ""}

def run_tests():
    return {"note": "(simulated)", "result": "14 passed"}

def git_log(limit=5):
    return {"note": "(simulated)", "commits": ["a1b2c3 Fix retry loop", "d4e5f6 Add rate limit"][:int(limit)]}

def send_task_notification(task_id):
    return {"note": "(simulated)", "notified_task": int(task_id)}

def restart_webhook_service():
    return {"note": "(simulated)", "result": "webhook service restarted"}

# ---------------- the two scoped tools used by the role toolsets ----------------
def load_document(path):
    """Constrained replacement for fetch_url: repository documents only, never URLs."""
    clean = path.strip().lstrip("./")
    if "://" in clean or not (clean.startswith("docs/") and clean.endswith(".md") or clean in ("README.md", "CLAUDE.md", "AGENTS.md")):
        raise ToolError("validation", False,
                        "load_document only loads repository documents: docs/*.md, README.md, CLAUDE.md, AGENTS.md. URLs and other files are not allowed.",
                        allowedExamples=["docs/CONCEPTS.md", "README.md"])
    p, ls = repo_lines(clean)
    return {"path": p, "content": "\n".join(ls)[:6000]}

def verify_fact(claim):
    """Scoped cross-role tool: only simple task facts. Anything else goes through the coordinator."""
    m = re.search(r"task\s*#?(\d+)\s+is\s+(open|in_progress|in progress|done)", claim.lower())
    if m:
        task = get_task_by_id(m.group(1)); want = m.group(2).replace(" ", "_")
        return {"verdict": "supported" if task["status"] == want else "contradicted", "actual_status": task["status"]}
    m = re.search(r"(\d+)\s+tasks?\s+(?:are|is)\s+(open|in_progress|in progress|done)", claim.lower())
    if m:
        n = count_tasks_by_status(m.group(2).replace(" ", "_"))["count"]
        return {"verdict": "supported" if n == int(m.group(1)) else "contradicted", "actual_count": n}
    raise ToolError("validation", False,
                    "verify_fact only checks simple task facts such as 'task 3 is done' or '2 tasks are in_progress'. For anything else, ask the coordinator.",
                    routeTo="coordinator")


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
        try:
            reply(mid, {"content": [{"type": "text", "text": json.dumps(globals()[p["name"]](**(p.get("arguments") or {})))}], "isError": False})
        except ToolError as err:
            reply(mid, {"content": [{"type": "text", "text": json.dumps(err.body)}], "isError": True})
        except Exception as exc:
            reply(mid, {"content": [{"type": "text", "text": json.dumps({"errorCategory": "transient", "isRetryable": True, "message": str(exc)})}], "isError": True})
    else:
        reply(mid, {})
