from __future__ import annotations

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.pyannote_provider import PyannoteProvider


class DiarizationService:
    def __init__(self, provider: PyannoteProvider) -> None:
        self.provider = provider

    def run(self, transcript: TranscriptDocument, audio_path):
        raise NotImplementedError("Segment diarization merge is not implemented yet")
