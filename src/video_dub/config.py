from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1


class TTSConfig(BaseModel):
    voice: str = "kazakh-default"


class VideoConfig(BaseModel):
    subtitle_mode: str = "soft"


class PipelineConfig(BaseModel):
    enable_diarization: bool = False


class AppConfig(BaseModel):
    run_root: Path = Field(default=Path("runs"))
    source_language: str = "en"
    target_language: str = "kk"
    subtitle_language: str = "zh"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)


def load_config(path: Path) -> AppConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
