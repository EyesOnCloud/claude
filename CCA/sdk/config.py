"""Environment passed to every Agent SDK session so it runs on Bedrock."""
import os

BEDROCK_ENV = {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
    "ANTHROPIC_MODEL": os.environ.get("ANTHROPIC_MODEL", "us.anthropic.claude-sonnet-4-6"),
}
if os.environ.get("AWS_PROFILE"):
    BEDROCK_ENV["AWS_PROFILE"] = os.environ["AWS_PROFILE"]
