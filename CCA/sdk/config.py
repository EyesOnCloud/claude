"""Environment passed to every Agent SDK session so it runs on Bedrock."""
import os

BEDROCK_ENV = {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
    "ANTHROPIC_MODEL": os.environ.get("ANTHROPIC_MODEL", "us.anthropic.claude-sonnet-4-6"),
}
if os.environ.get("AWS_PROFILE"):
    BEDROCK_ENV["AWS_PROFILE"] = os.environ["AWS_PROFILE"]
EOF
cat > hello_sdk.py <<'EOF'
"""The smallest possible Agent SDK agent."""
import asyncio

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from config import BEDROCK_ENV


async def main():
    options = ClaudeAgentOptions(env=BEDROCK_ENV, max_turns=1)
    async for msg in query(prompt="Reply with exactly: SDK_OK", options=options):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock):
                    print("CLAUDE:", b.text)
        elif isinstance(msg, ResultMessage):
            print(f"[result] subtype={msg.subtype} session_id={msg.session_id}")


asyncio.run(main())
