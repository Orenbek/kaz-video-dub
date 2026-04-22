from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Segment(BaseModel):
    id: str
    start: float
    end: float
    text_en: str
    speaker: Optional[str] = None
    text_kk: Optional[str] = None
    subtitle_zh: Optional[str] = None
    tts_path: Optional[Path] = None
    tts_duration: Optional[float] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class DiarizationSpan(BaseModel):
    start: float
    end: float
    speaker: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)
