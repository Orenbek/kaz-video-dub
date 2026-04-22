from __future__ import annotations

from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_tts_provider import GeminiTTSProvider


class SynthesisService:
    def __init__(self, provider: GeminiTTSProvider) -> None:
        self.provider = provider

    def run(self, transcript: TranscriptDocument):
        raise NotImplementedError("Segment TTS orchestration is not implemented yet")
