from __future__ import annotations

import subprocess
from pathlib import Path

from video_dub.config import AppConfig
from video_dub.ffmpeg.commands import extract_audio_command


class AudioExtractor:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build_command(self, input_video: Path, output_audio: Path) -> str:
        return extract_audio_command(
            input_video=input_video,
            output_audio=output_audio,
            sample_rate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
        )

    def extract(self, input_video: Path, output_audio: Path) -> Path:
        output_audio.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(input_video, output_audio)
        subprocess.run(command, shell=True, check=True)
        return output_audio
