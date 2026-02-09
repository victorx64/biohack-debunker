from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List

from .errors import TranscriptFetchError
from .schemas import TranscriptSegment, VideoMetadata
from .transcript_parser import build_transcript, parse_captions
from .yt_dlp_runner import YtDlpRunner


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
    def __init__(self, runner: YtDlpRunner) -> None:
        self._runner = runner

    async def fetch_transcript(self, url: str) -> TranscriptResult:
        info = await asyncio.to_thread(self._runner.extract_info, url)
        choice = self._pick_caption(info)
        caption_text = await asyncio.to_thread(
            self._runner.download_caption,
            url,
            choice.language,
            choice.is_auto,
            choice.ext,
        )
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

    def _pick_caption(self, info: Dict) -> _CaptionChoice:
        subtitles = info.get("subtitles") or {}
        auto_captions = info.get("automatic_captions") or {}

        # Prefer original audio language from metadata.
        original_language = self._video_language(info)
        if original_language:
            manual_choice = self._select_caption_for_language(
                subtitles,
                original_language,
                is_auto=False,
                prefer_original=True,
            )
            if manual_choice:
                self._log_choice(manual_choice, info)
                return manual_choice

            auto_choice = self._select_caption_for_language(
                auto_captions,
                original_language,
                is_auto=True,
                prefer_original=True,
            )
            if auto_choice:
                self._log_choice(auto_choice, info)
                return auto_choice

            manual_choice = self._select_caption_for_language(
                subtitles,
                original_language,
                is_auto=False,
                prefer_original=False,
            )
            if manual_choice:
                self._log_choice(manual_choice, info)
                return manual_choice

            auto_choice = self._select_caption_for_language(
                auto_captions,
                original_language,
                is_auto=True,
                prefer_original=False,
            )
            if auto_choice:
                self._log_choice(auto_choice, info)
                return auto_choice

        # Fallbacks when original language is missing from metadata.
        manual_choice = self._select_caption_any(subtitles, is_auto=False, prefer_original=True)
        if manual_choice:
            self._log_choice(manual_choice, info)
            return manual_choice

        auto_choice = self._select_caption_any(auto_captions, is_auto=True, prefer_original=True)
        if auto_choice:
            self._log_choice(auto_choice, info)
            return auto_choice

        manual_choice = self._select_caption_any(subtitles, is_auto=False, prefer_original=False)
        if manual_choice:
            self._log_choice(manual_choice, info)
            return manual_choice

        auto_choice = self._select_caption_any(auto_captions, is_auto=True, prefer_original=False)
        if auto_choice:
            self._log_choice(auto_choice, info)
            return auto_choice

        raise TranscriptFetchError("No subtitles or automatic captions available")

    def _log_choice(self, choice: _CaptionChoice, info: Dict) -> None:
        logger = logging.getLogger(__name__)
        logger.info(
            "Selected captions language=%s auto=%s ext=%s video_language=%s",
            choice.language,
            choice.is_auto,
            choice.ext,
            info.get("language"),
        )

    def _select_caption_any(
        self,
        caption_map: Dict[str, List[Dict]],
        is_auto: bool,
        prefer_original: bool,
    ) -> _CaptionChoice | None:
        for lang in sorted(caption_map.keys()):
            entry = self._pick_best_entry(caption_map.get(lang) or [], prefer_original)
            if entry:
                return _CaptionChoice(lang, entry["url"], entry["ext"], is_auto)
        return None

    def _select_caption_for_language(
        self,
        caption_map: Dict[str, List[Dict]],
        language: str,
        is_auto: bool,
        prefer_original: bool,
    ) -> _CaptionChoice | None:
        entry = self._pick_best_entry(caption_map.get(language) or [], prefer_original)
        if entry:
            return _CaptionChoice(language, entry["url"], entry["ext"], is_auto)
        return None

    def _pick_best_entry(self, entries: List[Dict], prefer_original: bool) -> Dict | None:
        if not entries:
            return None
        if prefer_original:
            original_entries = [entry for entry in entries if not entry.get("is_translated")]
            entry = self._pick_format(original_entries)
            if entry:
                return entry
        return self._pick_format(entries)

    def _video_language(self, info: Dict) -> str | None:
        for key in ("language", "audio_language", "original_language"):
            value = info.get(key)
            if value:
                return value
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
