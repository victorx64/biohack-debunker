from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TranscriptionRequest(BaseModel):
    youtube_url: str = Field(..., min_length=10)


class VideoMetadata(BaseModel):
    youtube_id: str
    title: str | None = None
    channel: str | None = None
    duration: int | None = None
    thumbnail_url: str | None = None
    webpage_url: str | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionResponse(BaseModel):
    youtube_url: str
    video: VideoMetadata
    transcript: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    took_ms: int
    warnings: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    use_stubs: bool
