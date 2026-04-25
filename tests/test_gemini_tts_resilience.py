from types import SimpleNamespace

from video_dub.providers.gemini_tts_provider import GeminiTTSConfig, GeminiTTSProvider


def test_extract_pcm_bytes_reads_inline_audio() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig())
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(inline_data=SimpleNamespace(data=b"pcm-bytes"), text=None)
                    ]
                )
            )
        ]
    )

    assert provider._extract_pcm_bytes(response) == b"pcm-bytes"


def test_extract_pcm_bytes_rejects_text_only_response() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig())
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(inline_data=None, text="text instead of audio")
                    ]
                )
            )
        ]
    )

    try:
        provider._extract_pcm_bytes(response)
    except RuntimeError as exc:
        assert "returned text instead of audio" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for text-only TTS response")
