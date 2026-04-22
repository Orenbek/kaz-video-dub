from __future__ import annotations

from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.whisperx_provider import WhisperXProvider


class TranscriptionService:
    def __init__(self, provider: WhisperXProvider) -> None:
        self.provider = provider

    def run(self, audio_path):
        return self.provider.transcribe_and_align(audio_path)
