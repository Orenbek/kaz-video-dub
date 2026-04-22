from __future__ import annotations

from video_dub.models.segment import Segment


class GeminiTranslateProvider:
    def translate_to_kazakh(self, segments: list[Segment]) -> list[Segment]:
        raise NotImplementedError("Gemini translation integration is not implemented yet")

    def translate_to_chinese_subtitles(self, segments: list[Segment]) -> list[Segment]:
        raise NotImplementedError("Gemini subtitle translation integration is not implemented yet")
