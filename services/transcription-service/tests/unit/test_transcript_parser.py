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


def test_build_transcript_merges_word_overlap() -> None:
    srt = """1
00:00:01,000 --> 00:00:02,000
After this video you will get a clear plan

2
00:00:02,000 --> 00:00:03,000
you will get a clear plan on what to eat
"""
    segments = parse_captions(srt, "srt")
    assert build_transcript(segments) == (
        "After this video you will get a clear plan on what to eat"
    )


def test_parse_captions_trims_overlap_in_segments() -> None:
    srt = """1
00:00:01,000 --> 00:00:02,000
We should avoid sugar and refined carbs

2
00:00:02,000 --> 00:00:03,000
refined carbs and focus on protein
"""
    segments = parse_captions(srt, "srt")
    assert len(segments) == 2
    assert segments[0].text == "We should avoid sugar and refined carbs"
    assert segments[1].text == "and focus on protein"
