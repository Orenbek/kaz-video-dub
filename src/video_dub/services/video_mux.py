from __future__ import annotations

from pathlib import Path

from video_dub.ffmpeg.commands import mux_soft_subtitle_command


class VideoMuxService:
    def build_soft_subtitle_command(
        self,
        input_video: Path,
        dub_audio: Path,
        subtitle_srt: Path,
        output_video: Path,
    ) -> str:
        return mux_soft_subtitle_command(input_video, dub_audio, subtitle_srt, output_video)
