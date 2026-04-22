from types import SimpleNamespace

from video_dub.providers.gemini_translate_provider import GeminiTranslateConfig, GeminiTranslateProvider


def test_extract_text_response_prefers_response_text() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=False))
    response = SimpleNamespace(text="  translated text  ")

    assert provider._extract_text_response(response) == "translated text"


def test_extract_text_response_collects_parts() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=False))
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text=" first "),
                        SimpleNamespace(text="second"),
                    ]
                )
            )
        ],
    )

    assert provider._extract_text_response(response) == "first\nsecond"
