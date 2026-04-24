from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


class WhisperXConfig(BaseModel):
    model_name: str = "large-v3"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    batch_size: int = 8
    vad_method: str = "pyannote"


class WhisperXProvider:
    def __init__(self, config: WhisperXConfig | None = None) -> None:
        self.config = config or WhisperXConfig()

    def transcribe_and_align(self, audio_path: Path) -> TranscriptDocument:
        import whisperx  # type: ignore[import-untyped]

        model = whisperx.load_model(
            self.config.model_name,
            device=self.config.device,
            compute_type=self.config.compute_type,
            language=self.config.language,
            vad_method=self.config.vad_method,
        )
        transcription = model.transcribe(str(audio_path), batch_size=self.config.batch_size)

        align_model, metadata = whisperx.load_align_model(
            language_code=self.config.language,
            device=self.config.device,
        )
        aligned = whisperx.align(
            transcription["segments"],
            align_model,
            metadata,
            str(audio_path),
            self.config.device,
            return_char_alignments=False,
        )
        return TranscriptDocument(
            source_audio_path=audio_path,
            language=self.config.language,
            segments=self._build_segments(aligned.get("segments", [])),
            metadata={
                "provider": "whisperx",
                "model_name": self.config.model_name,
            },
        )

    def _build_segments(self, raw_segments: list[dict[str, Any]]) -> list[Segment]:
        segments: list[Segment] = []
        for index, raw in enumerate(raw_segments, start=1):
            text = (raw.get("text") or "").strip()
            if not text:
                continue
            start = float(raw.get("start") or 0.0)
            end = float(raw.get("end") or start)
            segments.append(
                Segment(
                    id=f"seg_{index:04d}",
                    start=start,
                    end=end,
                    text_en=text,
                )
            )
        return segments
