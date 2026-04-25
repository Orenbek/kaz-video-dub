from video_dub.providers.mlx_whisper_provider import MLXWhisperProvider


def test_mlx_whisper_normalizes_segments_for_alignment() -> None:
    provider = MLXWhisperProvider()

    segments = provider._normalize_segments(
        [
            {"start": 0.0, "end": 1.0, "text": " Hello "},
            {"start": 1.0, "end": 2.0, "text": "   "},
            {"start": 3.0, "end": 3.0, "text": "empty duration"},
        ]
    )

    assert segments == [{"start": 0.0, "end": 1.0, "text": "Hello"}]


def test_mlx_whisper_build_segments_skips_empty_text() -> None:
    provider = MLXWhisperProvider()

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
