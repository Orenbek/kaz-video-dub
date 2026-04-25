from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


class MLXWhisperConfig(BaseModel):
    model_name: str = "mlx-community/whisper-large-v3-turbo"
    language: str = "en"
    align_device: str = "cpu"
    word_timestamps: bool = False


class MLXWhisperProvider:
    def __init__(self, config: MLXWhisperConfig | None = None) -> None:
        self.config = config or MLXWhisperConfig()

    def transcribe_and_align(self, audio_path: Path) -> TranscriptDocument:
        import mlx_whisper  # type: ignore[import-untyped]
        import whisperx  # type: ignore[import-untyped]

        transcription = cast(
            dict[str, Any],
            mlx_whisper.transcribe(
                str(audio_path),
                path_or_hf_repo=self.config.model_name,
                language=self.config.language,
                task="transcribe",
                word_timestamps=self.config.word_timestamps,
                verbose=None,
            ),
        )
        raw_segments_payload = transcription.get("segments", [])
        raw_segments = self._normalize_segments(
            raw_segments_payload if isinstance(raw_segments_payload, list) else []
        )
        if not raw_segments:
            return TranscriptDocument(
                source_audio_path=audio_path,
                language=self.config.language,
                segments=[],
                metadata={
                    "provider": "mlx_whisper",
                    "model_name": self.config.model_name,
                    "aligned": False,
                },
            )

        align_model, metadata = whisperx.load_align_model(
            language_code=self.config.language,
            device=self.config.align_device,
        )
        aligned = whisperx.align(
            raw_segments,
            align_model,
            metadata,
            str(audio_path),
            self.config.align_device,
            return_char_alignments=False,
        )
        return TranscriptDocument(
            source_audio_path=audio_path,
            language=self.config.language,
            segments=self._build_segments(aligned.get("segments", [])),
            metadata={
                "provider": "mlx_whisper",
                "model_name": self.config.model_name,
                "alignment_provider": "whisperx",
                "alignment_device": self.config.align_device,
            },
        )

    def _normalize_segments(self, raw_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for raw in raw_segments:
            text = (raw.get("text") or "").strip()
            if not text:
                continue
            start = float(raw.get("start") or 0.0)
            end = float(raw.get("end") or start)
            if end <= start:
                continue
            segments.append({"start": start, "end": end, "text": text})
        return segments

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
