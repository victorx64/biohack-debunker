from __future__ import annotations

import json
import logging
import os
from json import JSONDecodeError
from typing import Any

import httpx

logger = logging.getLogger("analysis_service.llm")


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
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:500]
            logger.error("openai request failed status=%s body=%s", exc.response.status_code, body)
            raise
        except Exception:
            logger.exception("openai request failed")
            raise
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(_extract_json(content))
        except JSONDecodeError:
            recovered = _recover_json_list(content)
            if recovered is not None:
                logger.warning("openai json decode recovered stage=%s items=%s", system_prompt, len(recovered))
                return recovered
            snippet = (content or "")[:500]
            logger.error("openai json decode failed stage=%s content=%s", system_prompt, snippet)
            raise

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
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = (exc.response.text or "")[:500]
            logger.error("anthropic request failed status=%s body=%s", exc.response.status_code, body)
            raise
        except Exception:
            logger.exception("anthropic request failed")
            raise
        content = "".join(block.get("text", "") for block in data.get("content", []))
        try:
            return json.loads(_extract_json(content))
        except JSONDecodeError:
            recovered = _recover_json_list(content)
            if recovered is not None:
                logger.warning("anthropic json decode recovered stage=%s items=%s", system_prompt, len(recovered))
                return recovered
            snippet = (content or "")[:500]
            logger.error("anthropic json decode failed stage=%s content=%s", system_prompt, snippet)
            raise


def _extract_json(text: str) -> str:
    object_start = text.find("{")
    array_start = text.find("[")
    if object_start == -1 and array_start == -1:
        return text
    if object_start == -1:
        start = array_start
    elif array_start == -1:
        start = object_start
    else:
        start = min(object_start, array_start)
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1:
        return text
    return text[start : end + 1]


def _recover_json_list(text: str) -> list[Any] | None:
    extracted = _extract_json(text)
    start = extracted.find("[")
    if start == -1:
        return None
    decoder = json.JSONDecoder()
    items: list[Any] = []
    idx = start + 1
    length = len(extracted)
    while idx < length:
        while idx < length and extracted[idx] in " \t\r\n,":
            idx += 1
        if idx >= length or extracted[idx] == "]":
            break
        try:
            item, next_idx = decoder.raw_decode(extracted, idx)
        except JSONDecodeError:
            break
        items.append(item)
        idx = next_idx
    return items or None
