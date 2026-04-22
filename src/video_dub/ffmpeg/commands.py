from __future__ import annotations

from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


def quote(path: Path | str) -> str:
    return f'"{path}"'


def extract_audio_command(input_video: Path, output_audio: Path, sample_rate: int, channels: int) -> str:
    return (
        "ffmpeg -y "
        f"-i {quote(input_video)} "
        f"-vn -ac {channels} -ar {sample_rate} -c:a pcm_s16le {quote(output_audio)}"
    )


def build_compose_segment_filter(segment: Segment, index: int) -> str:
    delay_ms = max(0, round(segment.start * 1000))
    target_duration = segment.target_duration or 0.0
    tts_duration = segment.tts_duration or 0.0
    if target_duration > tts_duration:
        pad_ms = round((target_duration - tts_duration) * 1000)
        return f"[{index}:a]apad=pad_dur={pad_ms}ms,adelay={delay_ms}|{delay_ms}[a{index}]"
    return f"[{index}:a]adelay={delay_ms}|{delay_ms}[a{index}]"


def compose_dub_audio_command(transcript: TranscriptDocument, output_audio: Path) -> str:
    valid_segments = [segment for segment in transcript.segments if segment.tts_path]
    if not valid_segments:
        raise ValueError("No TTS segment audio paths found for composition")

    input_args = " ".join(f"-i {quote(segment.tts_path)}" for segment in valid_segments)
    filter_parts: list[str] = []
    mix_inputs: list[str] = []
    for index, segment in enumerate(valid_segments):
        filter_parts.append(build_compose_segment_filter(segment, index))
        mix_inputs.append(f"[a{index}]")
    filter_complex = ";".join(filter_parts) + f";{''.join(mix_inputs)}amix=inputs={len(valid_segments)}:normalize=0[out]"
    return (
        "ffmpeg -y "
        f"{input_args} "
        f"-filter_complex '{filter_complex}' "
        "-map '[out]' -c:a pcm_s16le "
        f"{quote(output_audio)}"
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
