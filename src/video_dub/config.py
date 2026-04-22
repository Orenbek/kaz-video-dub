from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1


class TTSConfig(BaseModel):
    voice: str = "Kore"
    model_name: str = "gemini-3.1-flash-tts-preview"
    use_stub: bool = True
    sample_rate: int = 24000
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class VideoConfig(BaseModel):
    subtitle_mode: str = "soft"


class PipelineConfig(BaseModel):
    enable_diarization: bool = False


class TranslationConfig(BaseModel):
    provider: str = "gemini"
    use_stub: bool = True
    model_name: str = "gemini-2.5-pro"
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class AppConfig(BaseModel):
    run_root: Path = Field(default=Path("runs"))
    source_language: str = "en"
    target_language: str = "kk"
    subtitle_language: str = "zh"
    audio: AudioConfig = Field(default_factory=AudioConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)


def load_config(path: Path) -> AppConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
