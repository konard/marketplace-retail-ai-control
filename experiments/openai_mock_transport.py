"""Check that the openai SDK talks to an httpx.MockTransport fake."""

import json

import httpx
import openai


def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    print("PATH", request.url.path, "TOOLS", [t["function"]["name"] for t in body.get("tools", [])])
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "margin_breakdown", "arguments": "{}"}}]}}],
    })


client = openai.OpenAI(base_url="http://llm.test/v1", api_key="k", max_retries=0,
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)))
r = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}],
    tools=[{"type": "function", "function": {"name": "margin_breakdown", "description": "d", "parameters": {"type": "object", "properties": {}}}}])
print(r.choices[0].message.tool_calls[0].function.name, openai.__version__)
