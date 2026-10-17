cat > config.py <<'EOF'
"""Settings for every Agent SDK session. The model comes ONLY from the environment
(ANTHROPIC_MODEL, or BEDROCK_MODEL_ID if that is not set)."""
import os

MODEL = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("BEDROCK_MODEL_ID", "")
if not MODEL:
    raise SystemExit("ANTHROPIC_MODEL / BEDROCK_MODEL_ID is not set. Export it first.")
# An inference-profile ARN contains its own region (arn:aws:bedrock:<region>:...), so use that one
REGION = MODEL.split(":")[3] if MODEL.startswith("arn:") else os.environ.get("AWS_REGION", "us-east-1")

BEDROCK_ENV = {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": REGION,
    "ANTHROPIC_MODEL": MODEL,
    # Point every model alias at the same profile, so subagents and background tasks
    # never try to call a model your account is not allowed to use
    "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
}
if os.environ.get("AWS_PROFILE"):
    BEDROCK_ENV["AWS_PROFILE"] = os.environ["AWS_PROFILE"]
EOF
python -c "import config; print(config.BEDROCK_ENV['ANTHROPIC_MODEL'])"
python hello_sdk.py
