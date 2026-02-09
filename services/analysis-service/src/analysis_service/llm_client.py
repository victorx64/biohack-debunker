from __future__ import annotations

import json
import os
from typing import Any

import httpx


class LLMClient:
    def __init__(
        self,
        provider: str,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
        temperature: float,
        max_tokens: int,
        timeout: float = 30.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return self.provider in {"openai", "anthropic"} and bool(self.model) and bool(self.api_key)

    async def generate_json(self, system_prompt: str, user_prompt: str) -> Any:
        if not self.enabled:
            raise RuntimeError("LLM client is not configured")
        if self.provider == "openai":
            return await self._openai_json(system_prompt, user_prompt)
        if self.provider == "anthropic":
            return await self._anthropic_json(system_prompt, user_prompt)
        raise RuntimeError(f"Unsupported provider: {self.provider}")

    async def _openai_json(self, system_prompt: str, user_prompt: str) -> Any:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(_extract_json(content))

    async def _anthropic_json(self, system_prompt: str, user_prompt: str) -> Any:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = "".join(block.get("text", "") for block in data.get("content", []))
        return json.loads(_extract_json(content))


def _extract_json(text: str) -> str:
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        return text
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1:
        return text
    return text[start : end + 1]
