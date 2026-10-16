"""Session management with the Agent SDK.
  python sessions_lab.py analyze   # start a named investigation session
  python sessions_lab.py change    # modify a file on disk between work sessions
  python sessions_lab.py resume    # resume BY NAME and tell the agent exactly what changed
  python sessions_lab.py fork      # fork_session: two strategies from one baseline
  python sessions_lab.py fresh     # new session seeded with a structured summary
  python sessions_lab.py list      # show saved session names"""
import asyncio
import json
import sys
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

from config import BEDROCK_ENV

HERE = Path(__file__).parent.resolve()
APP = HERE / "sample_app"
NAMES = HERE / "sessions.json"
SUMMARY = HERE / "summary.txt"

SAMPLE = {
    "auth.py": "from tokens import make_token\n\ndef login(db, user, pw):\n"
               "    row = db.query(f\"SELECT * FROM users WHERE name='{user}'\")\n"
               "    if row and row.pw == pw:\n        return make_token(user)\n",
    "tokens.py": "import time\n\ndef make_token(user):\n    return f\"{user}:{int(time.time())}\"\n\n"
                 "def check_token(tok):\n    user, ts = tok.split(':')\n    return True\n",
    "api.py": "from tokens import check_token\n\ndef get_orders(db, tok, user_id):\n"
              "    if check_token(tok):\n        return db.orders(user_id)\n",
}
NEW_TOKENS = ("import hmac, hashlib, time\nSECRET = b'dev-secret'\n\ndef make_token(user):\n"
              "    ts = str(int(time.time()))\n"
              "    sig = hmac.new(SECRET, f'{user}:{ts}'.encode(), hashlib.sha256).hexdigest()\n"
              "    return f'{user}:{ts}:{sig}'\n\ndef check_token(tok, max_age=3600):\n"
              "    user, ts, sig = tok.split(':')\n"
              "    good = hmac.new(SECRET, f'{user}:{ts}'.encode(), hashlib.sha256).hexdigest()\n"
              "    return hmac.compare_digest(sig, good) and time.time() - int(ts) < max_age\n")


def names():
    return json.loads(NAMES.read_text()) if NAMES.exists() else {}


def save(name, sid):
    d = names()
    d[name] = sid
    NAMES.write_text(json.dumps(d, indent=2))
    print(f"\n  saved session '{name}' -> {sid}")


async def run(prompt, **extra):
    sid, final = None, ""
    options = ClaudeAgentOptions(env=BEDROCK_ENV, cwd=str(APP), max_turns=25,
                                 allowed_tools=["Read", "Glob", "Grep"], **extra)
    async for m in query(prompt=prompt, options=options):
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, ToolUseBlock):
                    print(f"  -> {b.name}({json.dumps(b.input)[:90]})")
                elif isinstance(b, TextBlock) and b.text.strip():
                    print(f"CLAUDE: {b.text.strip()}\n")
        elif isinstance(m, ResultMessage):
            sid, final = m.session_id, m.result or ""
            print(f"[result] {m.subtype}, session={sid}")
    return sid, final


async def analyze():
    APP.mkdir(exist_ok=True)
    for f, src in SAMPLE.items():
        (APP / f).write_text(src)
    sid, final = await run("This legacy codebase has no tests. Map its structure, identify the highest-risk areas "
                           "and propose a prioritized test plan. End with a JSON block named SUMMARY with "
                           "files_analyzed, key_risks and test_plan.")
    save("testing-investigation", sid)
    SUMMARY.write_text(final)


def change():
    if not APP.exists():
        sys.exit("Run 'python sessions_lab.py analyze' first.")
    (APP / "tokens.py").write_text(NEW_TOKENS)
    print("tokens.py now uses HMAC-signed tokens with max_age. The saved session still remembers the OLD file.")


async def resume():
    await run("Since your analysis, tokens.py was modified: tokens are now HMAC-signed and check_token verifies the "
              "signature and a max_age. The other files are unchanged. Re-read ONLY tokens.py, then tell me which of "
              "your earlier risks and test-plan items change.",
              resume=names()["testing-investigation"])


async def fork():
    base = names()["testing-investigation"]
    for name, prompt in {
        "fork-unit-first": "Take a unit-test-first strategy: list pytest tests per function, using mocks. Plan only.",
        "fork-integration-first": "Take an integration-first strategy: design end-to-end tests through "
                                  "api.get_orders with a fake db. Plan only.",
    }.items():
        print(f"\n===== branch: {name} =====")
        sid, _ = await run(prompt, resume=base, fork_session=True)
        assert sid != base, "a fork must get its own session id"
        save(name, sid)
    print(f"\nBaseline unchanged: testing-investigation -> {base}")


async def fresh():
    prior = SUMMARY.read_text()[-3000:] if SUMMARY.exists() else "(none)"
    sid, _ = await run(f"You are continuing a test-planning investigation. Prior findings (may be outdated):\n{prior}\n\n"
                       "Known change since then: tokens.py now uses HMAC-signed tokens with max_age. Verify against "
                       "the current files and produce the updated prioritized test plan.")
    save("testing-fresh", sid)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd in ("analyze", "resume", "fork", "fresh"):
        asyncio.run({"analyze": analyze, "resume": resume, "fork": fork, "fresh": fresh}[cmd]())
    elif cmd == "change":
        change()
    elif cmd == "list":
        print(json.dumps(names(), indent=2))
    else:
        print(__doc__)
