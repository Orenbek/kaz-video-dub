from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from video_dub.models.segment import DiarizationSpan


class PyannoteConfig(BaseModel):
    model_name: str = "pyannote/speaker-diarization-3.1"
    device: str = "cpu"
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    auth_token_env: str = "HF_TOKEN"


class PyannoteProvider:
    def __init__(
        self,
        config: PyannoteConfig | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.config = config or PyannoteConfig()
        self.auth_token = auth_token

    def diarize(self, audio_path: Path) -> list[DiarizationSpan]:
        from whisperx.diarize import DiarizationPipeline  # type: ignore[import-untyped]

        pipeline = DiarizationPipeline(
            model_name=self.config.model_name,
            use_auth_token=self._resolve_auth_token(),
            device=self.config.device,
        )
        diarize_df = pipeline(
            str(audio_path),
            num_speakers=self.config.num_speakers,
            min_speakers=self.config.min_speakers,
            max_speakers=self.config.max_speakers,
        )
        return self._build_spans(diarize_df)

    def _resolve_auth_token(self) -> str | None:
        return (
            self.auth_token
            or os.getenv(self.config.auth_token_env)
            or os.getenv("HUGGINGFACE_TOKEN")
            or os.getenv("HUGGINGFACE_HUB_TOKEN")
            or os.getenv("PYANNOTE_AUTH_TOKEN")
        )

    def _build_spans(self, diarize_df: Any) -> list[DiarizationSpan]:
        spans: list[DiarizationSpan] = []
        for row in diarize_df.itertuples(index=False):
            start = float(row.start)
            end = float(row.end)
            if end <= start:
                continue
            spans.append(
                DiarizationSpan(
                    start=start,
                    end=end,
                    speaker=str(row.speaker),
                )
            )
        return sorted(spans, key=lambda span: (span.start, span.end, span.speaker))
