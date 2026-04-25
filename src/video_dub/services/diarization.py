from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Protocol

from video_dub.models.segment import DiarizationSpan, Segment
from video_dub.models.transcript import TranscriptDocument


class DiarizationProvider(Protocol):
    def diarize(self, audio_path: Path) -> list[DiarizationSpan]: ...


class DiarizationService:
    def __init__(self, provider: DiarizationProvider) -> None:
        self.provider = provider

    def run(self, transcript: TranscriptDocument, audio_path: Path) -> TranscriptDocument:
        spans = self.provider.diarize(audio_path)
        diarized_segments = [
            segment.model_copy(update={"speaker": self.assign_speaker(segment, spans)})
            for segment in transcript.segments
        ]
        metadata = {
            **transcript.metadata,
            "diarization": {
                "provider": "pyannote",
                "span_count": len(spans),
                "speaker_count": len({span.speaker for span in spans}),
                "assigned_segment_count": sum(
                    1 for segment in diarized_segments if segment.speaker is not None
                ),
            },
        }
        return transcript.model_copy(update={"segments": diarized_segments, "metadata": metadata})

    def assign_speaker(
        self,
        segment: Segment,
        spans: list[DiarizationSpan],
    ) -> str | None:
        overlaps: defaultdict[str, float] = defaultdict(float)
        for span in spans:
            overlap_seconds = self._overlap_seconds(
                segment.start,
                segment.end,
                span.start,
                span.end,
            )
            if overlap_seconds > 0:
                overlaps[span.speaker] += overlap_seconds
        if not overlaps:
            return None
        return sorted(overlaps.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _overlap_seconds(self, start_a: float, end_a: float, start_b: float, end_b: float) -> float:
        return max(0.0, min(end_a, end_b) - max(start_a, start_b))
