from __future__ import annotations

import html
import re
from typing import List

from .schemas import TranscriptSegment

_TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3}")


def parse_captions(content: str, ext: str | None = None) -> List[TranscriptSegment]:
    if not content:
        return []
    cleaned = _strip_header(content)
    segments = _parse_cues(cleaned)
    if segments:
        return segments
    if ext and ext.lower() not in {"vtt", "srt"}:
        return []
    return segments


def build_transcript(segments: List[TranscriptSegment]) -> str:
    return " ".join(segment.text for segment in segments).strip()


def _strip_header(content: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].strip().upper().startswith("WEBVTT"):
        lines = lines[1:]
    return "\n".join(lines)


def _parse_cues(content: str) -> List[TranscriptSegment]:
    lines = [line.rstrip("\n") for line in content.splitlines()]
    segments: List[TranscriptSegment] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.isdigit():
            index += 1
            continue
        if "-->" in line and _TIME_RE.search(line):
            start, end = _parse_time_range(line)
            index += 1
            text_lines: List[str] = []
            while index < len(lines) and lines[index].strip():
                text_lines.append(lines[index].strip())
                index += 1
            text = _normalize_text(" ".join(text_lines))
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))
            continue
        index += 1

    return segments


def _parse_time_range(line: str) -> tuple[float, float]:
    start_raw, end_raw = line.split("-->", 1)
    start = _parse_timestamp(start_raw.strip())
    end_part = end_raw.strip().split()[0]
    end = _parse_timestamp(end_part)
    return start, end


def _parse_timestamp(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_part = parts[2]
    else:
        hours = 0
        minutes = int(parts[0])
        seconds_part = parts[1]
    if "." in seconds_part:
        seconds_str, millis_str = seconds_part.split(".", 1)
    else:
        seconds_str, millis_str = seconds_part, "0"
    seconds = int(seconds_str)
    millis = int(millis_str.ljust(3, "0")[:3])
    return hours * 3600 + minutes * 60 + seconds + (millis / 1000)


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()
