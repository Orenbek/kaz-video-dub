from video_dub.providers.whisperx_provider import WhisperXProvider


def test_build_segments_skips_empty_text() -> None:
    provider = WhisperXProvider()
    segments = provider._build_segments(
        [
            {"start": 0.0, "end": 1.0, "text": " Hello "},
            {"start": 1.0, "end": 2.0, "text": "   "},
        ]
    )

    assert len(segments) == 1
    assert segments[0].id == "seg_0001"
    assert segments[0].text_en == "Hello"
    assert segments[0].start == 0.0
    assert segments[0].end == 1.0
