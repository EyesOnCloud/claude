"""Settings for every Agent SDK session, using a Claude API key."""
import os

if not os.environ.get("ANTHROPIC_API_KEY"):
    raise SystemExit("ANTHROPIC_API_KEY is not set. Run: export ANTHROPIC_API_KEY=sk-ant-...")

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SDK_ENV = {
    "CLAUDE_CODE_USE_BEDROCK": "0",          # make sure Bedrock mode is off
    "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
    "ANTHROPIC_MODEL": MODEL,
    # Point every alias at the same model so subagents/background tasks use it too
    "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
}
