"""TaskFlow tools that fail on purpose, for the structured-error lab (a tiny MCP server).
The TOOLSET env var picks toolsets/<TOOLSET>.json. Its "error_style" decides how failures look:
  "generic"    -> every failure is just "Operation failed" (a failed search even returns an empty result)
  "structured" -> failures carry errorCategory, isRetryable and a human-readable explanation
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLSET = json.load(open(os.path.join(HERE, "toolsets", os.environ["TOOLSET"] + ".json")))
STYLE = TOOLSET["error_style"]

TASKS = [
    {"id": 1, "title": "Fix invoice PDF export", "status": "open", "team": "platform"},
    {"id": 2, "title": "Rotate webhook signing secret", "status": "in_progress", "team": "platform"},
    {"id": 3, "title": "Migrate invoice archive", "status": "done", "team": "platform"},
    {"id": 4, "title": "Audit logs for PII", "status": "done", "team": "platform"},
    {"id": 5, "title": "Add rate limit to bulk-notify", "status": "in_progress", "team": "platform"},
    {"id": 6, "title": "Invoice reminder email copy", "status": "open", "team": "finance"},
]
VALID_STATUSES = ["open", "in_progress", "done"]
calls = {}   # how often each call has happened in this run (lets us fail the first attempts only)


def seen(key):
    calls[key] = calls.get(key, 0) + 1
    return calls[key]


class ToolError(Exception):
    def __init__(self, category, retryable, message, customer_message=None, **extra):
        self.category, self.retryable, self.message = category, retryable, message
        self.customer_message, self.extra = customer_message, extra


def find_task(task_id):
    task = next((t for t in TASKS if t["id"] == int(task_id)), None)
    if task is None:
        raise ToolError("validation", False, f"No task with id {task_id}", validIds=[t["id"] for t in TASKS])
    return task


def check_status(status):
    if status not in VALID_STATUSES:
        raise ToolError("validation", False, f"'{status}' is not a valid status", validValues=VALID_STATUSES)


def search_task_records(status=None, title_contains=None):
    if status:
        check_status(status)
    if status == "in_progress" and not title_contains and seen("search") == 1:
        if STYLE == "generic":
            return {"count": 0, "tasks": []}          # the failure is swallowed and looks like "no matches"
        raise ToolError("transient", True, "Task database timed out after 5s",
                        "The task database is briefly unavailable.", retryAfterSeconds=1)
    rows = [t for t in TASKS if (not status or t["status"] == status)
            and (not title_contains or title_contains.lower() in t["title"].lower())]
    return {"count": len(rows), "tasks": rows}        # count 0 here is a valid, successful answer


def get_task_by_id(task_id):
    return find_task(task_id)


def update_task_status(task_id, status):
    check_status(status)
    task = find_task(task_id)
    if task["team"] == "finance":
        raise ToolError("permission", False, "Caller is not a member of the finance team",
                        f"Task {task['id']} belongs to the finance team. Ask a finance team member to update it.")
    if task["status"] == "done" and status != "done":
        raise ToolError("business", False, "Business rule: completed tasks cannot be reopened",
                        "Completed tasks are locked and cannot be reopened. Create a new task for the follow-up work.")
    task["status"] = status
    return {"id": task["id"], "status": task["status"]}


def send_task_notification(task_id):
    task = find_task(task_id)
    if task["team"] == "finance":
        raise ToolError("permission", False, "Caller may not notify finance-team assignees",
                        f"Task {task['id']} belongs to the finance team. Ask them to send this notification.")
    if task["status"] == "done":
        raise ToolError("business", False, "Business rule: no notifications for completed tasks",
                        f"Task {task['id']} is already done, so its assignee is not notified.")
    if task["id"] == 5:                               # this webhook receiver is down for the whole run
        raise ToolError("transient", True, "Webhook receiver returned 503 Service Unavailable (request not processed)",
                        "The notification service is temporarily unavailable.", retryAfterSeconds=2)
    if task["id"] == 2 and seen("notify-2") <= 2:     # this one times out twice, then works
        raise ToolError("transient", True, "Webhook receiver returned 503 Service Unavailable (request not processed)",
                        "The notification service is temporarily unavailable.", retryAfterSeconds=1)
    return {"notified_task": task["id"]}


def error_result(err):
    if STYLE == "generic":
        text = "Operation failed"
    else:
        body = {"errorCategory": err.category, "isRetryable": err.retryable, "message": err.message}
        if err.customer_message:
            body["customerMessage"] = err.customer_message
        body.update(err.extra)
        text = json.dumps(body)
    return {"content": [{"type": "text", "text": text}], "isError": True}


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
            out = globals()[p["name"]](**(p.get("arguments") or {}))
            reply(mid, {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False})
        except ToolError as err:
            reply(mid, error_result(err))
        except Exception:
            reply(mid, error_result(ToolError("transient", True, "Unexpected server error")))
    else:
        reply(mid, {})
