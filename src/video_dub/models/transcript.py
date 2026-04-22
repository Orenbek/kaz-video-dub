from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from video_dub.models.segment import Segment


class TranscriptDocument(BaseModel):
    source_audio_path: Path
    language: str
    segments: list[Segment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
