from __future__ import annotations

from typing import Protocol

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


class TranslationProvider(Protocol):
    def translate_to_kazakh(self, segments: list[Segment]) -> list[Segment]: ...

    def translate_to_chinese_subtitles(self, segments: list[Segment]) -> list[Segment]: ...


class TranslationService:
    def __init__(self, provider: TranslationProvider) -> None:
        self.provider = provider

    def to_kazakh(self, transcript: TranscriptDocument) -> TranscriptDocument:
        translated_segments = self.provider.translate_to_kazakh(transcript.segments)
        return transcript.model_copy(update={"segments": translated_segments})

    def to_chinese_subtitles(self, transcript: TranscriptDocument) -> TranscriptDocument:
        translated_segments = self.provider.translate_to_chinese_subtitles(transcript.segments)
        return transcript.model_copy(update={"segments": translated_segments})
