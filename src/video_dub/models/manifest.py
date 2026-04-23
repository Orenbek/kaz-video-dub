from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "done", "skipped", "failed"]


def default_steps() -> dict[str, StepStatus]:
    return {
        "extract_audio": "pending",
        "transcribe": "pending",
        "align": "pending",
        "diarize": "pending",
        "translate": "pending",
        "subtitle": "pending",
        "tts": "pending",
        "compose_audio": "pending",
        "mux_video": "pending",
    }


class DurationSummary(BaseModel):
    total_segments: int = 0
    preferred_count: int = 0
    acceptable_count: int = 0
    too_short_count: int = 0
    too_long_count: int = 0
    manual_review_count: int = 0
    avg_abs_duration_error: float = 0.0
    time_stretch_applied_count: int = 0
    trim_trailing_silence_applied_count: int = 0
    pad_silence_applied_count: int = 0


class RunManifest(BaseModel):
    job_id: str
    input_video: Path | str | None = None
    source_language: str = "en"
    target_language: str = "kk"
    subtitle_language: str = "zh"
    artifacts: dict[str, str] = Field(default_factory=dict)
    duration_summary: DurationSummary = Field(default_factory=DurationSummary)
    steps: dict[str, StepStatus] = Field(default_factory=default_steps)
