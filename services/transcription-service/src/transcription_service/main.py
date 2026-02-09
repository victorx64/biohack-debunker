from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

import httpx
from fastapi import FastAPI, HTTPException

from .schemas import HealthResponse, TranscriptionRequest, TranscriptionResponse, VideoMetadata
from .youtube_client import TranscriptFetchError, YouTubeClient


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


USE_STUBS = _env_bool("TRANSCRIPTION_USE_STUBS", True)
MAX_TRANSCRIPT_CHARS = int(os.getenv("TRANSCRIPTION_MAX_CHARS", "120000"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = httpx.AsyncClient(timeout=30)
    app.state.youtube_client = YouTubeClient(http_client=app.state.http_client)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Transcription Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", use_stubs=USE_STUBS)


@app.post("/transcription", response_model=TranscriptionResponse)
async def transcribe(request: TranscriptionRequest) -> TranscriptionResponse:
    start = time.perf_counter()
    warnings: List[str] = []

    if USE_STUBS:
        warnings.append("Stub mode enabled; returning canned transcript.")
        response = _stub_response(request.youtube_url)
        response.took_ms = int((time.perf_counter() - start) * 1000)
        response.warnings = warnings
        return response

    client: YouTubeClient = app.state.youtube_client
    try:
        result = await client.fetch_transcript(request.youtube_url)
    except TranscriptFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    transcript = result.transcript
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS].rstrip() + "..."
        warnings.append("Transcript truncated to max length.")

    if result.is_auto:
        warnings.append("Used automatic captions; quality may be lower.")

    took_ms = int((time.perf_counter() - start) * 1000)
    return TranscriptionResponse(
        youtube_url=request.youtube_url,
        video=result.video,
        transcript=transcript,
        segments=result.segments,
        took_ms=took_ms,
        warnings=warnings,
    )


def _stub_response(url: str) -> TranscriptionResponse:
    video = VideoMetadata(
        youtube_id="dQw4w9WgXcQ",
        title="Sample Biohacking Video",
        channel="Biohack Demo",
        duration=420,
        thumbnail_url="https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        webpage_url=url,
    )
    segments = [
        {"start": 0.0, "end": 5.0, "text": "Welcome to the biohacking rundown."},
        {"start": 5.0, "end": 12.5, "text": "Today we discuss sleep, supplements, and recovery."},
        {"start": 12.5, "end": 20.0, "text": "Remember to check claims against real evidence."},
    ]
    transcript = " ".join(segment["text"] for segment in segments)
    return TranscriptionResponse(
        youtube_url=url,
        video=video,
        transcript=transcript,
        segments=segments,
        took_ms=0,
        warnings=[],
    )
