from __future__ import annotations

from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_translate_provider import GeminiTranslateProvider


class TranslationService:
    def __init__(self, provider: GeminiTranslateProvider) -> None:
        self.provider = provider

    def to_kazakh(self, transcript: TranscriptDocument) -> TranscriptDocument:
        translated_segments = self.provider.translate_to_kazakh(transcript.segments)
        return transcript.model_copy(update={"segments": translated_segments})

    def to_chinese_subtitles(self, transcript: TranscriptDocument) -> TranscriptDocument:
        translated_segments = self.provider.translate_to_chinese_subtitles(transcript.segments)
        return transcript.model_copy(update={"segments": translated_segments})
