from __future__ import annotations

import math
import os
import time
import wave
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from video_dub.models.segment import Segment
from video_dub.providers.gemini_retry import (
    build_gemini_http_options,
    is_retryable_gemini_error,
)
from video_dub.providers.gemini_tts.prompts import (
    DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE,
    build_tts_prompt,
)
from video_dub.providers.gemini_tts.voices import validate_voice_name


class GeminiTTSConfig(BaseModel):
    model_name: str = "gemini-3.1-flash-tts-preview"
    prompt_preamble: str = DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE
    language: str = "kk"
    api_key_env: str = "GEMINI_API_KEY"
    use_stub: bool = True
    sample_rate: int = 24000
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    request_timeout_seconds: float | None = 120.0


class GeminiTTSProvider:
    def __init__(self, config: GeminiTTSConfig | None = None) -> None:
        self.config = config or GeminiTTSConfig()

    def synthesize_segment(self, segment: Segment, output_path: Path, voice: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = (segment.text_kk or segment.text_en).strip()
        if not text:
            raise RuntimeError(f"Segment {segment.id} has no text for TTS")
        if self.config.use_stub:
            self._write_stub_wav(output_path, text)
            return output_path
        self.validate_voice_name(voice)
        prompt = self.build_tts_prompt(
            text,
            target_duration_seconds=segment.target_duration or segment.duration,
            language=self.config.language,
        )
        return self._synthesize_with_gemini(prompt, output_path, voice, segment.id)

    def validate_voice_name(self, voice_name: str) -> None:
        validate_voice_name(voice_name)

    def build_tts_prompt(
        self,
        text: str,
        target_duration_seconds: float | None = None,
        language: str | None = None,
    ) -> str:
        return build_tts_prompt(
            text=text,
            prompt_preamble=self.config.prompt_preamble,
            target_duration_seconds=target_duration_seconds,
            language=language or self.config.language,
        )

    def _synthesize_with_gemini(
        self, text: str, output_path: Path, voice: str, segment_id: str
    ) -> Path:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing {self.config.api_key_env} for Gemini TTS")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        client = genai.Client(
            api_key=api_key,
            http_options=self._build_http_options(types),
        )
        last_error: Exception | None = None
        attempt_count = 0
        for attempt in range(1, self.config.max_retries + 1):
            attempt_count = attempt
            try:
                response = client.models.generate_content(
                    model=self.config.model_name,
                    contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            )
                        ),
                    ),
                )
                pcm_data = self._extract_pcm_bytes(response)
                self._write_pcm_wav(output_path, pcm_data)
                return output_path
            except Exception as exc:
                last_error = exc
                if attempt == self.config.max_retries or not is_retryable_gemini_error(exc):
                    break
                print(
                    f"[tts] Gemini retry {attempt + 1}/{self.config.max_retries} "
                    f"for {segment_id} after error: {exc}"
                )
                time.sleep(self.config.retry_delay_seconds)
        raise RuntimeError(
            "Gemini TTS failed for "
            f"segment {segment_id} after {attempt_count} attempt(s): {last_error}"
        ) from last_error

    def _build_http_options(self, types_module: Any) -> Any:
        return build_gemini_http_options(types_module, self.config.request_timeout_seconds)

    def _extract_pcm_bytes(self, response: Any) -> bytes:
        try:
            parts = response.candidates[0].content.parts
        except (AttributeError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini TTS response did not contain candidates content") from exc

        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None)
            if data:
                return data

        text_parts = [
            part.text.strip() for part in parts if getattr(part, "text", None) and part.text.strip()
        ]
        if text_parts:
            raise RuntimeError(
                "Gemini TTS returned text instead of audio data; "
                "retry may help for preview-model behavior"
            )
        raise RuntimeError("Gemini TTS response did not contain inline audio data")

    def _write_pcm_wav(self, output_path: Path, pcm_data: bytes) -> None:
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.config.sample_rate)
            wav_file.writeframes(pcm_data)

    def _write_stub_wav(self, output_path: Path, text: str) -> None:
        sample_rate = self.config.sample_rate
        duration = max(0.4, min(6.0, len(text) * 0.06))
        frame_count = int(sample_rate * duration)
        frequency = 440.0
        amplitude = 10000

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames = bytearray()
            for i in range(frame_count):
                value = int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate)))
                frames += value.to_bytes(2, byteorder="little", signed=True)
            wav_file.writeframes(bytes(frames))
