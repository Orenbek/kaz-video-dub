from __future__ import annotations

from pathlib import Path

from video_dub.models.segment import DiarizationSpan


class PyannoteProvider:
    def diarize(self, audio_path: Path) -> list[DiarizationSpan]:
        raise NotImplementedError("pyannote integration is not implemented yet")
