from __future__ import annotations

from pathlib import Path

from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.whisperx_provider import WhisperXProvider


class TranscriptionService:
    def __init__(self, provider: WhisperXProvider) -> None:
        self.provider = provider

    def run(self, audio_path: Path) -> TranscriptDocument:
        return self.provider.transcribe_and_align(audio_path)
