from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "done", "skipped", "failed"]


class RunManifest(BaseModel):
    job_id: str
    input_video: Path
    source_language: str = "en"
    target_language: str = "kk"
    subtitle_language: str = "zh"
    artifacts: dict[str, str] = Field(default_factory=dict)
    steps: dict[str, StepStatus] = Field(
        default_factory=lambda: {
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
    )
