from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List

import httpx
from yt_dlp import YoutubeDL

from .schemas import TranscriptSegment, VideoMetadata
from .transcript_parser import build_transcript, parse_captions


class TranscriptFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptResult:
    video: VideoMetadata
    segments: List[TranscriptSegment]
    transcript: str
    language: str
    is_auto: bool
    source_ext: str


@dataclass(frozen=True)
class _CaptionChoice:
    language: str
    url: str
    ext: str
    is_auto: bool


class YouTubeClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def fetch_transcript(self, url: str, language: str | None = None) -> TranscriptResult:
        info = await asyncio.to_thread(self._extract_info, url)
        choice = self._pick_caption(info, language)
        caption_text = await self._download_caption(choice.url)
        segments = parse_captions(caption_text, choice.ext)
        if not segments:
            raise TranscriptFetchError("No usable captions found in subtitle file")

        video = VideoMetadata(
            youtube_id=str(info.get("id") or ""),
            title=info.get("title"),
            channel=info.get("channel") or info.get("uploader"),
            duration=info.get("duration"),
            thumbnail_url=info.get("thumbnail"),
            webpage_url=info.get("webpage_url"),
        )
        transcript = build_transcript(segments)

        return TranscriptResult(
            video=video,
            segments=segments,
            transcript=transcript,
            language=choice.language,
            is_auto=choice.is_auto,
            source_ext=choice.ext,
        )

    def _extract_info(self, url: str) -> Dict:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitlesformat": "vtt/srt",
        }
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def _download_caption(self, url: str) -> str:
        response = await self._http_client.get(url)
        response.raise_for_status()
        return response.text

    def _pick_caption(self, info: Dict, language: str | None) -> _CaptionChoice:
        subtitles = info.get("subtitles") or {}
        auto_captions = info.get("automatic_captions") or {}

        preferred = self._preferred_languages(language)
        manual_choice = self._select_caption(subtitles, preferred, is_auto=False)
        if manual_choice:
            return manual_choice

        auto_choice = self._select_caption(auto_captions, preferred, is_auto=True)
        if auto_choice:
            return auto_choice

        raise TranscriptFetchError("No subtitles or automatic captions available")

    def _preferred_languages(self, language: str | None) -> List[str]:
        if language:
            base = language.split("-")[0]
            return [language, base]
        return ["en", "en-US", "en-GB", "en-CA", "en-AU"]

    def _select_caption(
        self,
        caption_map: Dict[str, List[Dict]],
        preferred: List[str],
        is_auto: bool,
    ) -> _CaptionChoice | None:
        for lang in preferred:
            entry = self._pick_format(caption_map.get(lang) or [])
            if entry:
                return _CaptionChoice(lang, entry["url"], entry["ext"], is_auto)

        for lang in sorted(caption_map.keys()):
            entry = self._pick_format(caption_map.get(lang) or [])
            if entry:
                return _CaptionChoice(lang, entry["url"], entry["ext"], is_auto)
        return None

    def _pick_format(self, entries: List[Dict]) -> Dict | None:
        if not entries:
            return None
        preferred_exts = ["vtt", "srt", "ttml", "srv3", "json3"]
        for ext in preferred_exts:
            for entry in entries:
                if entry.get("ext") == ext:
                    return entry
        return entries[0]
