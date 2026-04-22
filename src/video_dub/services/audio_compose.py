from __future__ import annotations

from pathlib import Path

from video_dub.models.transcript import TranscriptDocument


class AudioComposeService:
    def build_ffmpeg_command(self, transcript: TranscriptDocument, output_path: Path) -> str:
        raise NotImplementedError("Dub audio composition is not implemented yet")
