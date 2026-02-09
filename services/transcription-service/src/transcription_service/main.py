from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from fastapi import FastAPI, HTTPException

from .errors import TranscriptFetchError
from .schemas import HealthResponse, TranscriptionRequest, TranscriptionResponse
from .youtube_client import YouTubeClient
from .yt_dlp_runner import ProcessYtDlpRunner


MAX_TRANSCRIPT_CHARS = int(os.getenv("TRANSCRIPTION_MAX_CHARS", "120000"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yt_dlp_bin = os.getenv("YTDLP_BIN", "yt-dlp")
    runner = ProcessYtDlpRunner(binary=yt_dlp_bin)
    app.state.youtube_client = YouTubeClient(runner=runner)
    yield


app = FastAPI(title="Transcription Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@app.post("/transcription", response_model=TranscriptionResponse)
async def transcribe(request: TranscriptionRequest) -> TranscriptionResponse:
    start = time.perf_counter()
    warnings: List[str] = []

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
