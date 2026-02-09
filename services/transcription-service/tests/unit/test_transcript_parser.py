from transcription_service.transcript_parser import build_transcript, parse_captions


def test_parse_srt() -> None:
    srt = """1
00:00:01,000 --> 00:00:02,500
Hello world.

2
00:00:02,500 --> 00:00:04,000
Second line.
"""
    segments = parse_captions(srt, "srt")
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 2.5
    assert segments[0].text == "Hello world."
    assert build_transcript(segments) == "Hello world. Second line."


def test_parse_vtt() -> None:
    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
First

00:00:01.000 --> 00:00:02.000
Second
"""
    segments = parse_captions(vtt, "vtt")
    assert len(segments) == 2
    assert segments[1].text == "Second"
