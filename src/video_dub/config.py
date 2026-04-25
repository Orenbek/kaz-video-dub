from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1


class TranscriptionConfig(BaseModel):
    provider: Literal["whisperx", "mlx_whisper"] = "whisperx"
    model_name: str = "large-v3"
    device: str = "cpu"
    compute_type: str = "int8"
    batch_size: int = 8
    vad_method: str = "pyannote"
    mlx_model_name: str = "mlx-community/whisper-large-v3-turbo"
    align_device: str = "cpu"
    mlx_word_timestamps: bool = False


class TTSConfig(BaseModel):
    voice: str = "Kore"
    gemini_voice_names: dict[str, str] = Field(default_factory=dict)
    gemini_prompt_preamble: str | None = None
    model_name: str = "gemini-3.1-flash-tts-preview"
    sample_rate: int = 24000
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    request_timeout_seconds: float | None = 120.0


class TTSAlignmentConfig(BaseModel):
    enabled: bool = True
    preferred_ratio_tolerance: float = 0.12
    max_ratio_tolerance: float = 0.25
    enable_time_stretch: bool = True
    max_time_stretch_ratio: float = 0.30
    min_time_stretch_improvement_seconds: float = 0.05
    pad_with_silence: bool = True
    allow_minor_overhang_seconds: float = 0.25
    trim_trailing_silence: bool = True
    max_trailing_silence_trim_seconds: float = 1.0
    manual_review_on_failure: bool = True


class VideoConfig(BaseModel):
    subtitle_mode: Literal["soft", "hard"] = "soft"


class DiarizationConfig(BaseModel):
    model_name: str = "pyannote/speaker-diarization-3.1"
    device: str = "cpu"
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None


class TranslationConfig(BaseModel):
    provider: str = "gemini"
    model_name: str = "gemini-flash-latest"
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    request_timeout_seconds: float | None = 60.0


class AppConfig(BaseModel):
    run_root: Path = Field(default=Path("runs"))
    source_language: str = "en"
    target_language: str = "kk"
    subtitle_language: str = "zh"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    tts_alignment: TTSAlignmentConfig = Field(default_factory=TTSAlignmentConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    diarization: DiarizationConfig = Field(default_factory=DiarizationConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)


def load_config(path: Path) -> AppConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
