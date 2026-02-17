from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx

from .config import Settings
from .db import create_pool, update_analysis_status
from .observability import configure_logging, set_analysis_id
from .redis_client import create_redis
from .schemas import AnalysisCreateRequest
from .services.analysis_queue import AnalysisJob, AnalysisQueue
from .services.orchestrator import Orchestrator


logger = logging.getLogger(__name__)


class AnalysisWorker:
    def __init__(
        self,
        queue: AnalysisQueue,
        orchestrator: Orchestrator,
        pool,
        settings: Settings,
    ) -> None:
        self._queue = queue
        self._orchestrator = orchestrator
        self._pool = pool
        self._settings = settings

    async def run_forever(self) -> None:
        while True:
            job = await self._queue.dequeue(timeout_seconds=self._settings.analysis_worker_poll_timeout)
            if job is None:
                continue
            await self._process_job(job)

    async def _process_job(self, job: AnalysisJob) -> None:
        analysis_id = UUID(job.analysis_id)
        set_analysis_id(job.analysis_id)
        payload = AnalysisCreateRequest(**job.request)
        try:
            await self._orchestrator.run_analysis(
                self._pool,
                analysis_id,
                payload,
                request_id=job.request_id,
                correlation_id=job.correlation_id,
            )
        except Exception as exc:
            next_attempt = job.attempt + 1
            if next_attempt <= self._settings.analysis_max_retries:
                delay = self._settings.analysis_retry_backoff_seconds * next_attempt
                await update_analysis_status(self._pool, analysis_id, "pending")
                logger.warning(
                    "analysis_job_retry_scheduled",
                    extra={
                        "status": "retrying",
                        "attempt": next_attempt,
                        "max_retries": self._settings.analysis_max_retries,
                        "delay_seconds": delay,
                    },
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._queue.enqueue(
                    AnalysisJob(
                        analysis_id=job.analysis_id,
                        request=job.request,
                        request_id=job.request_id,
                        correlation_id=job.correlation_id,
                        attempt=next_attempt,
                    )
                )
                return

            await update_analysis_status(self._pool, analysis_id, "failed")
            await self._queue.push_dead_letter(job, error=str(exc))
            logger.exception("analysis_job_failed_to_dlq")


async def _run() -> None:
    settings = Settings()
    configure_logging("analysis-worker")
    pool = await create_pool(settings.database_dsn)
    redis = await create_redis(settings.redis_url)
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))
    queue = AnalysisQueue(
        client=redis,
        queue_name=settings.analysis_queue_name,
        dlq_name=settings.analysis_dlq_name,
    )
    orchestrator = Orchestrator(http_client, settings)
    worker = AnalysisWorker(queue=queue, orchestrator=orchestrator, pool=pool, settings=settings)

    try:
        logger.info("analysis_worker_started")
        await worker.run_forever()
    finally:
        await http_client.aclose()
        await redis.close()
        await pool.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
