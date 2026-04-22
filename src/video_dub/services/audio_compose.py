from __future__ import annotations

import subprocess
from pathlib import Path

from video_dub.ffmpeg.commands import compose_dub_audio_command
from video_dub.models.transcript import TranscriptDocument


class AudioComposeService:
    def build_ffmpeg_command(self, transcript: TranscriptDocument, output_path: Path) -> str:
        return compose_dub_audio_command(transcript, output_path)

    def compose(self, transcript: TranscriptDocument, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_ffmpeg_command(transcript, output_path)
        subprocess.run(command, shell=True, check=True)
        return output_path
