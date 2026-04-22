from video_dub.providers.gemini_translate_provider import GeminiTranslateConfig, GeminiTranslateProvider
from video_dub.models.segment import Segment


def test_stub_kazakh_translation_sets_text_kk() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True))
    segments = [Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello there")]

    translated = provider.translate_to_kazakh(segments)

    assert translated[0].text_kk == "[kk stub] Hello there"
    assert translated[0].subtitle_zh is None


def test_stub_chinese_translation_sets_subtitle() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True))
    segments = [Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello there")]

    translated = provider.translate_to_chinese_subtitles(segments)

    assert translated[0].subtitle_zh == "[zh stub] Hello there"
    assert translated[0].text_kk is None
