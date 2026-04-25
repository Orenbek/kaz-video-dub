from __future__ import annotations

from pathlib import Path
from typing import Protocol

from video_dub.models.transcript import TranscriptDocument


class TranscriptionProvider(Protocol):
    def transcribe_and_align(self, audio_path: Path) -> TranscriptDocument: ...


class TranscriptionService:
    def __init__(self, provider: TranscriptionProvider) -> None:
        self.provider = provider

    def run(self, audio_path: Path) -> TranscriptDocument:
        return self.provider.transcribe_and_align(audio_path)
