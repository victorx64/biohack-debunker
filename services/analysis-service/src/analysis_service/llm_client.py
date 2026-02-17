from __future__ import annotations

import asyncio
import json
import logging
from json import JSONDecodeError
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("analysis_service.llm")
_LOG_PROMPT_MAX_CHARS = 3000
_LOG_STAGE_MAX_CHARS = 40


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
        stage_routes: dict[str, list["LLMRoute"]] | None = None,
        max_fallbacks_per_stage: int = 2,
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
        self.max_fallbacks_per_stage = max_fallbacks_per_stage
        self.stage_routes = {
            key: value[: self.max_fallbacks_per_stage + 1]
            for key, value in (stage_routes or {}).items()
            if value
        }
        self.default_route = LLMRoute(
            provider=self.provider,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

    @property
    def enabled(self) -> bool:
        routes = [self.default_route]
        for stage_routes in self.stage_routes.values():
            routes.extend(stage_routes)
        return any(route.enabled for route in routes)

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        trace: dict[str, Any] | None = None,
        stage: str | None = None,
    ) -> Any:
        if not self.enabled:
            raise RuntimeError("LLM client is not configured")
        return await self._generate_with_routes(
            system_prompt,
            user_prompt,
            trace=trace,
            return_usage=False,
            stage=stage,
        )

    async def generate_json_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        trace: dict[str, Any] | None = None,
        stage: str | None = None,
    ) -> tuple[Any, "LLMUsage"]:
        if not self.enabled:
            raise RuntimeError("LLM client is not configured")
        result = await self._generate_with_routes(
            system_prompt,
            user_prompt,
            trace=trace,
            return_usage=True,
            stage=stage,
        )
        if not isinstance(result, tuple):
            raise RuntimeError("LLM usage is unavailable for this request")
        return result

    async def _generate_with_routes(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        trace: dict[str, Any] | None,
        return_usage: bool,
        stage: str | None,
    ) -> Any | tuple[Any, "LLMUsage"]:
        selected_stage = stage or _stage_from_system_prompt(system_prompt)
        stage_routes = self.stage_routes.get(selected_stage)
        routes = stage_routes or [self.default_route]
        if not routes:
            raise RuntimeError("No LLM routes configured")
        fallback_reason: str | None = None
        max_index = min(len(routes) - 1, self.max_fallbacks_per_stage)
        for route_index in range(max_index + 1):
            route = routes[route_index]
            fallback_used = route_index > 0
            if not route.enabled:
                fallback_reason = "route_not_configured"
                continue
            try:
                if route.provider == "openai":
                    return await self._openai_json(
                        system_prompt,
                        user_prompt,
                        trace,
                        return_usage=return_usage,
                        route=route,
                        stage=selected_stage,
                        fallback_used=fallback_used,
                        fallback_reason=fallback_reason,
                    )
                raise RuntimeError(f"Unsupported provider: {route.provider}")
            except Exception as exc:
                fallback_reason = _fallback_reason(exc)
                if route_index < max_index:
                    logger.warning(
                        "llm fallback route selected stage=%s provider_selected=%s model_selected=%s fallback_used=%s fallback_reason=%s",
                        selected_stage,
                        route.provider,
                        route.model,
                        True,
                        fallback_reason,
                    )
                    continue
                raise
        raise RuntimeError("LLM request failed before route execution")

    async def _openai_json(
        self,
        system_prompt: str,
        user_prompt: str,
        trace: dict[str, Any] | None = None,
        return_usage: bool = False,
        route: "LLMRoute" | None = None,
        stage: str | None = None,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
    ) -> Any | tuple[Any, "LLMUsage"]:
        selected_route = route or self.default_route
        if not selected_route.enabled:
            raise RuntimeError("LLM route is not configured")
        url = f"{selected_route.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {selected_route.api_key}"}
        payload = {
            "model": selected_route.model,
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
        selected_stage = stage or _stage_from_system_prompt(system_prompt)

        logger.info(
            "openai request prompts stage=%s provider_selected=%s model_selected=%s fallback_used=%s fallback_reason=%s trace=%s system_prompt=%s user_prompt=%s",
            selected_stage,
            selected_route.provider,
            selected_route.model,
            fallback_used,
            fallback_reason,
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
                logger.error(
                    "openai request failed stage=%s provider_selected=%s model_selected=%s attempt=%s fallback_used=%s fallback_reason=%s status=%s body=%s",
                    selected_stage,
                    selected_route.provider,
                    selected_route.model,
                    attempt + 1,
                    fallback_used,
                    fallback_reason,
                    exc.response.status_code,
                    body,
                )
                if attempt < self.max_retries and _should_retry_status(exc.response.status_code):
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise
            except httpx.ReadTimeout:
                logger.warning(
                    "openai request timed out stage=%s provider_selected=%s model_selected=%s attempt=%s/%s fallback_used=%s fallback_reason=%s",
                    selected_stage,
                    selected_route.provider,
                    selected_route.model,
                    attempt + 1,
                    self.max_retries + 1,
                    fallback_used,
                    fallback_reason,
                )
                if attempt < self.max_retries:
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise
            except Exception:
                logger.exception(
                    "openai request failed stage=%s provider_selected=%s model_selected=%s attempt=%s fallback_used=%s fallback_reason=%s",
                    selected_stage,
                    selected_route.provider,
                    selected_route.model,
                    attempt + 1,
                    fallback_used,
                    fallback_reason,
                )
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
                    "openai response missing content stage=%s provider_selected=%s model_selected=%s attempt=%s fallback_used=%s fallback_reason=%s "
                    "finish_reason=%s choice_keys=%s trace=%s response=%s",
                    selected_stage,
                    selected_route.provider,
                    selected_route.model,
                    attempt + 1,
                    fallback_used,
                    fallback_reason,
                    choice.get("finish_reason"),
                    list(choice.keys()),
                    trace or {},
                    response_snippet,
                )
                if attempt < self.max_retries:
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                raise ValueError("LLM returned empty content")
            logger.info(
                "openai response content stage=%s provider_selected=%s model_selected=%s attempt=%s fallback_used=%s fallback_reason=%s trace=%s content=%s",
                selected_stage,
                selected_route.provider,
                selected_route.model,
                attempt + 1,
                fallback_used,
                fallback_reason,
                trace or {},
                _truncate_for_log(content),
            )
            try:
                parsed = json.loads(_extract_json(content))
                if return_usage:
                    return parsed, usage
                return parsed
            except JSONDecodeError:
                if attempt < self.max_retries:
                    logger.warning(
                        "openai json decode failed, retrying stage=%s provider_selected=%s model_selected=%s attempt=%s/%s fallback_used=%s fallback_reason=%s",
                        selected_stage,
                        selected_route.provider,
                        selected_route.model,
                        attempt + 1,
                        self.max_retries + 1,
                        fallback_used,
                        fallback_reason,
                    )
                    await _sleep_backoff(self.backoff_seconds, attempt)
                    continue
                snippet = (content or "")[:500]
                logger.error(
                    "openai json decode retries exhausted stage=%s provider_selected=%s model_selected=%s attempts=%s fallback_used=%s fallback_reason=%s content=%s",
                    selected_stage,
                    selected_route.provider,
                    selected_route.model,
                    self.max_retries + 1,
                    fallback_used,
                    fallback_reason,
                    snippet,
                )
                raise
        raise ValueError("LLM request failed after retries")


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class LLMRoute:
    provider: str
    model: str | None
    api_key: str | None
    base_url: str | None

    @property
    def enabled(self) -> bool:
        return self.provider == "openai" and bool(self.model) and bool(self.api_key) and bool(self.base_url)

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


def _stage_from_system_prompt(system_prompt: str) -> str:
    compact = " ".join(system_prompt.split())
    if len(compact) <= _LOG_STAGE_MAX_CHARS:
        return compact
    return f"{compact[:_LOG_STAGE_MAX_CHARS]}..."


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, ValueError):
        return "invalid_response"
    if isinstance(exc, httpx.HTTPError):
        return "transport_error"
    return exc.__class__.__name__.lower()
