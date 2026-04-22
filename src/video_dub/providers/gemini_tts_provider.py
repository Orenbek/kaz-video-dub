from __future__ import annotations

from pathlib import Path

from video_dub.models.segment import Segment


class GeminiTTSProvider:
    def synthesize_segment(self, segment: Segment, output_path: Path, voice: str) -> Path:
        raise NotImplementedError("Gemini TTS integration is not implemented yet")
