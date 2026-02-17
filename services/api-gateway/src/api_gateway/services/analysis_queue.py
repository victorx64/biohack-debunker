from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis


@dataclass(frozen=True)
class AnalysisJob:
    analysis_id: str
    request: dict[str, Any]
    request_id: str | None = None
    correlation_id: str | None = None
    attempt: int = 0
    enqueued_at: str | None = None

    def to_json(self) -> str:
        payload = asdict(self)
        if not payload.get("enqueued_at"):
            payload["enqueued_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def from_json(cls, value: str) -> "AnalysisJob":
        payload = json.loads(value)
        return cls(
            analysis_id=str(payload["analysis_id"]),
            request=dict(payload.get("request") or {}),
            request_id=payload.get("request_id"),
            correlation_id=payload.get("correlation_id"),
            attempt=int(payload.get("attempt") or 0),
            enqueued_at=payload.get("enqueued_at"),
        )


class AnalysisQueue:
    def __init__(self, client: redis.Redis, queue_name: str, dlq_name: str) -> None:
        self._client = client
        self._queue_name = queue_name
        self._dlq_name = dlq_name

    async def enqueue(self, job: AnalysisJob) -> None:
        await self._client.rpush(self._queue_name, job.to_json())

    async def dequeue(self, timeout_seconds: int) -> AnalysisJob | None:
        result = await self._client.blpop([self._queue_name], timeout=timeout_seconds)
        if not result:
            return None
        _, payload = result
        return AnalysisJob.from_json(payload)

    async def push_dead_letter(self, job: AnalysisJob, error: str) -> None:
        payload = {
            "job": asdict(job),
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._client.rpush(self._dlq_name, json.dumps(payload, ensure_ascii=False))
