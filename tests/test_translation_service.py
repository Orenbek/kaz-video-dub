from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.translation import TranslationService


class FakeTranslationProvider:
    def translate_to_kazakh(self, segments: list[Segment]) -> list[Segment]:
        return [
            segment.model_copy(update={"text_kk": f"kk: {segment.text_en}"})
            for segment in segments
        ]

    def translate_to_chinese_subtitles(self, segments: list[Segment]) -> list[Segment]:
        return [
            segment.model_copy(update={"subtitle_zh": f"zh: {segment.text_en}"})
            for segment in segments
        ]


def test_translation_service_to_kazakh_updates_segments() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello")],
    )
    service = TranslationService(FakeTranslationProvider())

    translated = service.to_kazakh(transcript)

    assert translated.segments[0].text_kk == "kk: Hello"


def test_translation_service_to_chinese_updates_segments() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello")],
    )
    service = TranslationService(FakeTranslationProvider())

    translated = service.to_chinese_subtitles(transcript)

    assert translated.segments[0].subtitle_zh == "zh: Hello"
