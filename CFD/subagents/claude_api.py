"""One function to call Claude through the Anthropic API (uses ANTHROPIC_API_KEY)."""
import os

import anthropic

MODEL_ID = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


def call_claude(system, messages, tools=None, max_tokens=2048):
    kwargs = dict(model=MODEL_ID, max_tokens=max_tokens, system=system, messages=messages)
    if tools:
        kwargs["tools"] = tools
    resp = client.messages.create(**kwargs)
    # Return plain dicts, same shape the Bedrock version returned:
    # {"stop_reason": ..., "content": [{"type": "text"|"tool_use", ...}]}
    return {"stop_reason": resp.stop_reason,
            "content": [b.model_dump(exclude_none=True) for b in resp.content]}


if __name__ == "__main__":
    print(f"model={MODEL_ID}")
    r = call_claude("Reply with exactly: API_OK", [{"role": "user", "content": "ping"}], max_tokens=20)
    print(r["stop_reason"], "|", r["content"][0]["text"])
