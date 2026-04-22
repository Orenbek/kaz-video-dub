from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


class WhisperXConfig(BaseModel):
    model_name: str = "large-v3"
    language: str = "en"


class WhisperXProvider:
    def __init__(self, config: WhisperXConfig | None = None) -> None:
        self.config = config or WhisperXConfig()

    def transcribe_and_align(self, audio_path: Path) -> TranscriptDocument:
        raise NotImplementedError("WhisperX integration is not implemented yet")
