from __future__ import annotations

import asyncio
import json
import logging
import os
from json import JSONDecodeError
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("analysis_service.llm")
_LOG_PROMPT_MAX_CHARS = 3000


class LLMClient:
    def __init__(
        self,
        provider: str,
        model: str | None,
        api_key: str | None,
        base_url: str | None,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, str] | None = None,
        timeout: float = 30.0,
        read_timeout: float | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.response_format = response_format
        self.timeout = timeout
        self.read_timeout = read_timeout or timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    @property
    def enabled(self) -> bool:
        return self.provider == "openai" and bool(self.model) and bool(self.api_key)

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        trace: dict[str, Any] | None = None,
    ) -> Any:
        if not self.enabled:
            raise RuntimeError("LLM client is not configured")
        if self.provider == "openai":
            return await self._openai_json(
                system_prompt,
                user_prompt,
                trace,
                return_usage=False,
            )
        raise RuntimeError(f"Unsupported provider: {self.provider}")

    async def generate_json_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        trace: dict[str, Any] | None = None,
    ) -> tuple[Any, "LLMUsage"]:
        if not self.enabled:
            raise RuntimeError("LLM client is not configured")
        if self.provider == "openai":
            return await self._openai_json(
                system_prompt,
                user_prompt,
                trace,
                return_usage=True,
            )
        raise RuntimeError(f"Unsupported provider: {self.provider}")

    async def _openai_json(
        self,
        system_prompt: str,
        user_prompt: str,
        trace: dict[str, Any] | None = None,
        return_usage: bool = False,
    ) -> Any | tuple[Any, "LLMUsage"]:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "reasoning": {
                "effort": "none",
                "enabled": False,
            },
        }
        if self.response_format:
            payload["response_format"] = self.response_format

        logger.info(
            "openai request prompts provider=%s model=%s trace=%s system_prompt=%s user_prompt=%s",
            self.provider,
            self.model,
            trace or {},
            _truncate_for_log(system_prompt),
            _truncate_for_log(user_prompt),
        )

        for attempt in range(self.max_retries + 1):
            try:
                timeout = httpx.Timeout(self.timeout, read=self.read_timeout)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except httpx.HTTPStatusError as exc:
                body = (exc.response.text or "")[:500]
                logger.error("openai request failed status=%s body=%s", exc.response.status_code, body)
                if attempt < self.max_retries and _should_retry_status(exc.response.status_code):
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise
            except httpx.ReadTimeout:
                logger.warning(
                    "openai request timed out stage=%s attempt=%s/%s",
                    system_prompt,
                    attempt + 1,
                    self.max_retries + 1,
                )
                if attempt < self.max_retries:
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise
            except Exception:
                logger.exception("openai request failed")
                if attempt < self.max_retries:
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise
            content = _extract_openai_content(data)
            usage = _extract_openai_usage(data)
            if not content.strip():
                choice = (data.get("choices") or [{}])[0] or {}
                response_snippet = json.dumps(data, ensure_ascii=True)[:800]
                logger.error(
                    "openai response missing content stage=%s provider=%s model=%s attempt=%s "
                    "finish_reason=%s choice_keys=%s trace=%s response=%s",
                    system_prompt,
                    self.provider,
                    self.model,
                    attempt + 1,
                    choice.get("finish_reason"),
                    list(choice.keys()),
                    trace or {},
                    response_snippet,
                )
                if attempt < self.max_retries:
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise ValueError("LLM returned empty content")
            try:
                parsed = json.loads(_extract_json(content))
                if return_usage:
                    return parsed, usage
                return parsed
            except JSONDecodeError:
                recovered = _recover_json_list(content)
                if recovered is not None:
                    logger.warning(
                        "openai json decode recovered stage=%s items=%s",
                        system_prompt,
                        len(recovered),
                    )
                    if return_usage:
                        return recovered, usage
                    return recovered
                snippet = (content or "")[:500]
                logger.error("openai json decode failed stage=%s content=%s", system_prompt, snippet)
                raise
        raise ValueError("LLM request failed after retries")


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

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


def _extract_openai_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if content is None:
        content = choice.get("text")
    return content if isinstance(content, str) else ""


def _extract_openai_usage(data: dict[str, Any]) -> LLMUsage:
    usage = data.get("usage") or {}
    return LLMUsage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


async def _sleep_backoff(base_seconds: float, attempt: int) -> None:
    await asyncio.sleep(base_seconds * (2**attempt))


def _should_retry_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def _truncate_for_log(text: str, *, max_chars: int = _LOG_PROMPT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated, total_chars={len(text)}]"
