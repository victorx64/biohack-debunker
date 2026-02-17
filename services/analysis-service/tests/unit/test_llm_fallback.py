from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_service.llm_client import LLMClient, LLMRoute


def test_llm_fallback_uses_secondary_route_on_primary_failure(monkeypatch):
    calls: list[str] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            model = (json or {}).get("model")
            calls.append(model)
            request = httpx.Request("POST", url)
            if model == "primary-model":
                return httpx.Response(
                    status_code=500,
                    request=request,
                    json={"error": {"message": "primary failed"}},
                )
            return httpx.Response(
                status_code=200,
                request=request,
                json={
                    "choices": [{"message": {"content": json_module_dumps({"claims": []})}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 7},
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    client = LLMClient(
        provider="openai",
        model="default-model",
        api_key="test-key",
        base_url="https://example.invalid/v1",
        temperature=0.0,
        max_tokens=128,
        max_retries=0,
        stage_routes={
            "extraction": [
                LLMRoute(
                    provider="openai",
                    model="primary-model",
                    api_key="test-key",
                    base_url="https://example.invalid/v1",
                ),
                LLMRoute(
                    provider="openai",
                    model="fallback-model",
                    api_key="test-key",
                    base_url="https://example.invalid/v1",
                ),
            ]
        },
        max_fallbacks_per_stage=2,
    )

    result = asyncio.run(
        client.generate_json(
            system_prompt="extract",
            user_prompt="payload",
            stage="extraction",
        )
    )

    assert result == {"claims": []}
    assert calls == ["primary-model", "fallback-model"]


def json_module_dumps(payload: dict) -> str:
    return json.dumps(payload)