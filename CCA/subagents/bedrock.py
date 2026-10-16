"""One function to call Claude on Amazon Bedrock (Anthropic Messages format)."""
import json
import os

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
client = boto3.client("bedrock-runtime", region_name=REGION)


def call_claude(system, messages, tools=None, max_tokens=2048):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())


if __name__ == "__main__":
    print(f"region={REGION} model={MODEL_ID}")
    r = call_claude("Reply with exactly: BEDROCK_OK", [{"role": "user", "content": "ping"}], max_tokens=20)
    print(r["stop_reason"], "|", r["content"][0]["text"])
