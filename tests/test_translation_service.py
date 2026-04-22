from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_translate_provider import GeminiTranslateConfig, GeminiTranslateProvider
from video_dub.services.translation import TranslationService


def test_translation_service_to_kazakh_updates_segments() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello")],
    )
    service = TranslationService(GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True)))

    translated = service.to_kazakh(transcript)

    assert translated.segments[0].text_kk == "[kk stub] Hello"


def test_translation_service_to_chinese_updates_segments() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello")],
    )
    service = TranslationService(GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True)))

    translated = service.to_chinese_subtitles(transcript)

    assert translated.segments[0].subtitle_zh == "[zh stub] Hello"
