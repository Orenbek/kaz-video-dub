from __future__ import annotations

from pathlib import Path


def quote(path: Path | str) -> str:
    return f'"{path}"'


def extract_audio_command(input_video: Path, output_audio: Path, sample_rate: int, channels: int) -> str:
    return (
        "ffmpeg -y "
        f"-i {quote(input_video)} "
        f"-vn -ac {channels} -ar {sample_rate} -c:a pcm_s16le {quote(output_audio)}"
    )


def mux_soft_subtitle_command(input_video: Path, dub_audio: Path, subtitle_srt: Path, output_video: Path) -> str:
    return (
        "ffmpeg -y "
        f"-i {quote(input_video)} "
        f"-i {quote(dub_audio)} "
        f"-i {quote(subtitle_srt)} "
        "-map 0:v:0 -map 1:a:0 -map 2:0 "
        "-c:v copy -c:a aac -c:s mov_text "
        f"{quote(output_video)}"
    )
