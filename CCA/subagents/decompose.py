"""Two decomposition patterns.
  python decompose.py review  -> fixed prompt chain: per-file passes, then one cross-file pass
  python decompose.py plan    -> adaptive: plan, discover something, re-plan"""
import json
import sys

from bedrock import call_claude

REPO = {
    "auth.py": "def login(db, user, pw):\n    row = db.query(f\"SELECT * FROM users WHERE name='{user}'\")\n"
               "    if row and row.pw == pw:\n        return make_token(user)\n",
    "tokens.py": "import time\ndef make_token(user):\n    return f\"{user}:{int(time.time())}\"\n"
                 "def check_token(tok):\n    user, ts = tok.split(':')\n    return True\n",
    "api.py": "from tokens import check_token\ndef get_orders(db, tok, user_id):\n"
              "    if check_token(tok):\n        return db.orders(user_id)\n",
}


def text(resp):
    return "".join(b["text"] for b in resp["content"] if b["type"] == "text").strip()


def review():
    notes = {}
    for path, src in REPO.items():                                    # one focused pass per file
        notes[path] = text(call_claude(
            "Review ONE file. List concrete bugs and security issues, what it exports, and what it "
            "assumes about other modules. Be brief.",
            [{"role": "user", "content": f"File {path}:\n{src}"}], max_tokens=700))
        print(f"--- local pass: {path} ---\n{notes[path]}\n")
    summary = "\n\n".join(f"## {p}\n{n}" for p, n in notes.items())
    print("=== INTEGRATION PASS ===")
    print(text(call_claude(                                            # final cross-file pass
        "You do the CROSS-FILE review. Using the per-file notes, find issues that only appear when the files "
        "interact (broken contracts, trust assumptions, authorization flows).",
        [{"role": "user", "content": summary}], max_tokens=1000)))


def plan():
    fmt = 'Return ONLY JSON: {"tasks": [{"id": int, "task": str, "priority": int}], "changes": [str]}'
    v1 = text(call_claude("Map this codebase and produce a prioritized test plan. " + fmt,
                          [{"role": "user", "content": json.dumps(REPO)}], max_tokens=1000))
    print("PLAN v1:\n" + v1)
    discovery = ("While testing tokens.check_token we found it never validates anything, and "
                 "api.get_orders never checks that user_id matches the token's user.")
    v2 = text(call_claude("Revise the test plan given a new discovery. Re-prioritize, add or drop tasks, and "
                          "list what changed. " + fmt,
                          [{"role": "user", "content": f"Current plan:\n{v1}\n\nDiscovery: {discovery}"}],
                          max_tokens=1000))
    print("\nPLAN v2 (after discovery):\n" + v2)


if __name__ == "__main__":
    {"review": review, "plan": plan}[sys.argv[1]]()
