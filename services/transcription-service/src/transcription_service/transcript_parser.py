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
        return _dedupe_segments(segments)
    if ext and ext.lower() not in {"vtt", "srt"}:
        return []
    return segments


def build_transcript(segments: List[TranscriptSegment]) -> str:
    if not segments:
        return ""
    cleaned_segments = _dedupe_segments(segments)
    merged: List[str] = []
    for segment in cleaned_segments:
        if not segment.text:
            continue
        if not merged:
            merged.append(segment.text)
            continue
        merged[-1] = _merge_overlap(merged[-1], segment.text)
    return " ".join(merged).strip()


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


def _dedupe_segments(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    if not segments:
        return []
    cleaned: List[TranscriptSegment] = []
    for segment in segments:
        if not segment.text:
            continue
        if not cleaned:
            cleaned.append(segment)
            continue
        prev = cleaned[-1]
        if segment.text == prev.text:
            continue
        if segment.text.startswith(prev.text):
            cleaned[-1] = segment
            continue
        if prev.text.startswith(segment.text):
            continue
        overlap_words = _word_overlap_count(prev.text, segment.text)
        if overlap_words >= 2:
            trimmed = _strip_leading_words(segment.text, overlap_words)
            if not trimmed:
                continue
            cleaned.append(TranscriptSegment(start=segment.start, end=segment.end, text=trimmed))
            continue
        cleaned.append(segment)
    return cleaned


def _merge_overlap(left: str, right: str) -> str:
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right:
        return left
    if right.startswith(left):
        return right
    if left.startswith(right):
        return left
    merged = _merge_char_overlap(left, right)
    if merged != f"{left} {right}":
        return merged
    return _merge_word_overlap(left, right)


def _merge_char_overlap(left: str, right: str) -> str:
    max_len = min(len(left), len(right))
    overlap = 0
    for size in range(1, max_len + 1):
        if left[-size:] == right[:size]:
            overlap = size
    if overlap:
        return f"{left}{right[overlap:]}"
    return f"{left} {right}"


def _merge_word_overlap(left: str, right: str) -> str:
    left_tokens = _tokenize_words(left)
    right_tokens = _tokenize_words(right)
    if not left_tokens or not right_tokens:
        return f"{left} {right}"
    overlap = _word_overlap_count(left, right)
    if overlap >= 2:
        trimmed_right = " ".join(right_tokens[overlap:])
        return f"{left} {trimmed_right}".strip()
    return f"{left} {right}"


def _tokenize_words(text: str) -> List[str]:
    return re.findall(r"[\w\-']+", text.lower())


def _word_overlap_count(left: str, right: str) -> int:
    left_tokens = _tokenize_words(left)
    right_tokens = _tokenize_words(right)
    if not left_tokens or not right_tokens:
        return 0
    max_len = min(len(left_tokens), len(right_tokens), 12)
    overlap = 0
    for size in range(1, max_len + 1):
        if left_tokens[-size:] == right_tokens[:size]:
            overlap = size
    return overlap


def _strip_leading_words(text: str, count: int) -> str:
    if count <= 0:
        return text.strip()
    last_end = 0
    matches = list(re.finditer(r"[\w\-']+", text))
    if count >= len(matches):
        return ""
    last_end = matches[count - 1].end()
    trimmed = text[last_end:]
    trimmed = re.sub(r"^[^\w]+", "", trimmed)
    return trimmed.strip()


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
