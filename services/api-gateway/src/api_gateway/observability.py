from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


SERVICE_NAME = "api-gateway"

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)
_analysis_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("analysis_id", default="")


REQUEST_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "endpoint", "method", "status"],
)
REQUEST_ERRORS_TOTAL = Counter(
    "http_request_errors_total",
    "Total HTTP error responses",
    ["service", "endpoint", "method", "status"],
)
REQUEST_DURATION_MS = Histogram(
    "http_request_duration_ms",
    "HTTP request latency in milliseconds",
    ["service", "endpoint", "method"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)
PUBMED_CALLS_TOTAL = Counter(
    "pubmed_calls_total",
    "Total PubMed calls observed by service",
    ["service", "endpoint"],
)
LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total LLM token usage observed by service",
    ["service", "kind"],
)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get("")
        record.correlation_id = _correlation_id_ctx.get("")
        record.analysis_id = _analysis_id_ctx.get("")
        record.service = SERVICE_NAME
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": getattr(record, "service", SERVICE_NAME),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
            "correlation_id": getattr(record, "correlation_id", ""),
            "analysis_id": getattr(record, "analysis_id", ""),
        }
        for field in ("endpoint", "duration_ms", "status", "method"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service_name: str = SERVICE_NAME) -> None:
    global SERVICE_NAME
    SERVICE_NAME = service_name
    root_logger = logging.getLogger()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root_logger.setLevel(level)

    formatter = _JsonFormatter()
    has_handler = False
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
        handler.addFilter(_ContextFilter())
        has_handler = True
    if not has_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(_ContextFilter())
        root_logger.addHandler(stream_handler)


def set_analysis_id(analysis_id: str | None) -> None:
    _analysis_id_ctx.set(analysis_id or "")


def correlation_headers(request_id: str | None = None, correlation_id: str | None = None) -> dict[str, str]:
    rid = request_id or _request_id_ctx.get("")
    cid = correlation_id or _correlation_id_ctx.get("")
    headers: dict[str, str] = {}
    if rid:
        headers["X-Request-ID"] = rid
    if cid:
        headers["X-Correlation-ID"] = cid
    analysis_id = _analysis_id_ctx.get("")
    if analysis_id:
        headers["X-Analysis-ID"] = analysis_id
    return headers


def observe_pubmed_calls(count: int, endpoint: str = "internal") -> None:
    if count > 0:
        PUBMED_CALLS_TOTAL.labels(service=SERVICE_NAME, endpoint=endpoint).inc(count)


def observe_llm_tokens(kind: str, count: int) -> None:
    if count > 0:
        LLM_TOKENS_TOTAL.labels(service=SERVICE_NAME, kind=kind).inc(count)


async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    correlation_id = request.headers.get("X-Correlation-ID") or request_id
    analysis_id = request.headers.get("X-Analysis-ID") or ""
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    request.state.analysis_id = analysis_id

    _request_id_ctx.set(request_id)
    _correlation_id_ctx.set(correlation_id)
    _analysis_id_ctx.set(analysis_id)

    started = time.perf_counter()
    status_code = 500
    response: Response | None = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        endpoint = request.url.path
        method = request.method
        REQUEST_TOTAL.labels(
            service=SERVICE_NAME,
            endpoint=endpoint,
            method=method,
            status=str(status_code),
        ).inc()
        REQUEST_DURATION_MS.labels(
            service=SERVICE_NAME,
            endpoint=endpoint,
            method=method,
        ).observe(duration_ms)
        if status_code >= 400:
            REQUEST_ERRORS_TOTAL.labels(
                service=SERVICE_NAME,
                endpoint=endpoint,
                method=method,
                status=str(status_code),
            ).inc()
        logging.getLogger("observability").info(
            "request_completed",
            extra={
                "endpoint": endpoint,
                "duration_ms": duration_ms,
                "status": status_code,
                "method": method,
            },
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
