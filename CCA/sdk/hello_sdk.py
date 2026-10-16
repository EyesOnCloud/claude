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
