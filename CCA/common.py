"""
Shared helpers for Labs 1 and 2: a thin wrapper around Amazon Bedrock's
InvokeModel API using the Anthropic Messages format.

Why InvokeModel (not Converse)?  The CCA-F exam uses the Anthropic Messages
vocabulary -- stop_reason "tool_use" / "end_turn", tool_use / tool_result
content blocks -- and InvokeModel with anthropic_version "bedrock-2023-05-31"
returns exactly those shapes, so what you see in the labs matches the exam.
"""
import json
import os
import time

import boto3
from botocore.config import Config

REGION = os.environ.get("AWS_REGION", "us-east-1")
# Use an inference-profile ID your account has access to. List them with:
#   aws bedrock list-inference-profiles --region $AWS_REGION \
#     --query "inferenceProfileSummaries[?contains(inferenceProfileId,'anthropic')].inferenceProfileId"
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

_client = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, read_timeout=300),
)

VERBOSE = os.environ.get("LAB_VERBOSE", "1") == "1"


def log(tag, msg):
    if VERBOSE:
        print(f"\033[90m[{time.strftime('%H:%M:%S')}] {tag:<14}\033[0m {msg}")


def call_claude(system, messages, tools=None, max_tokens=2048, temperature=0.0):
    """One Messages API request through Bedrock. Returns the parsed response dict:
    {"content": [...blocks...], "stop_reason": "...", "usage": {...}, ...}"""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    resp = _client.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())


def text_of(content_blocks):
    """Concatenate the text blocks of an assistant response."""
    return "\n".join(b["text"] for b in content_blocks if b.get("type") == "text").strip()


def tool_uses(content_blocks):
    return [b for b in content_blocks if b.get("type") == "tool_use"]


def extract_json(text):
    """Pull the first JSON object/array out of a model reply (tolerates ```json fences)."""
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    start = min([i for i in (t.find("{"), t.find("[")) if i != -1], default=-1)
    if start == -1:
        raise ValueError(f"No JSON found in: {text[:200]}")
    return json.JSONDecoder().raw_decode(t[start:])[0]


def banner(title):
    print("\n" + "=" * 78 + f"\n  {title}\n" + "=" * 78)
