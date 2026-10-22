"""python3 ask_claude.py <toolset> "<request>"  -> shows each tool call, what came back, then the final answer."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
toolset, request = sys.argv[1], sys.argv[2]
config_path = os.path.join(tempfile.gettempdir(), f"taskflow-errors-{toolset}.json")
json.dump({"mcpServers": {"taskflow": {"command": sys.executable,
                                        "args": [os.path.join(HERE, "taskflow_tools_server.py")],
                                        "env": {"TOOLSET": toolset}}}}, open(config_path, "w"))
spec = json.load(open(os.path.join(HERE, "toolsets", toolset + ".json")))
cmd = ["claude", "-p", request, "--mcp-config", config_path, "--strict-mcp-config", "--tools", "",
       "--system-prompt", "\n".join(spec["system"]) + "\n", "--output-format", "stream-json", "--verbose",
       "--allowedTools", ",".join("mcp__taskflow__" + t["name"] for t in spec["tools"])]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
answer = ""
for line in result.stdout.splitlines():
    try: event = json.loads(line)
    except ValueError: continue
    if event.get("type") == "assistant":
        for block in event["message"]["content"]:
            if block.get("type") == "tool_use":
                print(f"CALL    {block['name'].replace('mcp__taskflow__', '')}  {json.dumps(block['input'])}")
    elif event.get("type") == "user":
        for block in event["message"]["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                body = block["content"] if isinstance(block["content"], str) else "".join(c.get("text", "") for c in block["content"])
                print(f"RESULT  isError={bool(block.get('is_error'))}  {body[:170]}")
    elif event.get("type") == "result":
        answer = event.get("result", "")
print("ANSWER", answer or result.stderr[-400:])
