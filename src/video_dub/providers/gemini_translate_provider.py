from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from video_dub.models.segment import Segment
from video_dub.providers.gemini_retry import (
    build_gemini_http_options,
    is_retryable_gemini_error,
)

TranslationMode = Literal["kk", "zh"]


class GeminiContentGenerator(Protocol):
    def generate_content(self, *, model: str, contents: str) -> Any: ...


class GeminiClientLike(Protocol):
    @property
    def models(self) -> GeminiContentGenerator: ...


class GeminiTranslateConfig(BaseModel):
    model_name: str = "gemini-flash-latest"
    api_key_env: str = "GEMINI_API_KEY"
    prompt_dir: Path = Path("configs/prompts")
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    request_timeout_seconds: float | None = 60.0


class GeminiTranslateProvider:
    def __init__(self, config: GeminiTranslateConfig | None = None) -> None:
        self.config = config or GeminiTranslateConfig()

    def translate_to_kazakh(self, segments: list[Segment]) -> list[Segment]:
        return self._translate_with_gemini(segments, mode="kk")

    def translate_to_chinese_subtitles(self, segments: list[Segment]) -> list[Segment]:
        return self._translate_with_gemini(segments, mode="zh")

    def _translate_with_gemini(
        self, segments: list[Segment], mode: TranslationMode
    ) -> list[Segment]:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing {self.config.api_key_env} for Gemini translation")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        prompt_name = (
            "translate_en_to_kk.txt" if mode == "kk" else "translate_en_to_zh_subtitle.txt"
        )
        system_prompt = (self.config.prompt_dir / prompt_name).read_text(encoding="utf-8")
        client = genai.Client(
            api_key=api_key,
            http_options=self._build_http_options(types),
        )

        print(
            f"[translate] Starting Gemini {mode} translation: "
            f"model={self.config.model_name} segments={len(segments)} "
            f"timeout={self._format_timeout()}"
        )
        translated_segments: list[Segment] = []
        for index, segment in enumerate(segments, start=1):
            print(f"[translate] {mode} {index}/{len(segments)} {segment.id}")
            prompt = (
                f"{system_prompt}\n\n"
                f"Return only the translated text for this segment.\n"
                f"Segment ID: {segment.id}\n"
                f"Source text: {segment.text_en}\n"
            )
            text = self._generate_text_with_retry(
                client=client,
                model_name=self.config.model_name,
                prompt=prompt,
                segment_id=segment.id,
                mode=mode,
            )
            if mode == "kk":
                translated_segments.append(segment.model_copy(update={"text_kk": text}))
            else:
                translated_segments.append(segment.model_copy(update={"subtitle_zh": text}))
        print(
            f"[translate] Finished Gemini {mode} translation: translated={len(translated_segments)}"
        )
        return translated_segments

    def _generate_text_with_retry(
        self,
        client: GeminiClientLike,
        model_name: str,
        prompt: str,
        segment_id: str,
        mode: TranslationMode,
    ) -> str:
        last_error: Exception | None = None
        attempt_count = 0
        for attempt in range(1, self.config.max_retries + 1):
            attempt_count = attempt
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = self._extract_text_response(response)
                if text:
                    return text
                raise RuntimeError("Gemini returned empty translation text")
            except Exception as exc:
                last_error = exc
                if attempt == self.config.max_retries or not is_retryable_gemini_error(exc):
                    break
                print(
                    f"[translate] Gemini {mode} retry {attempt + 1}/{self.config.max_retries} "
                    f"for {segment_id} after error: {exc}"
                )
                time.sleep(self.config.retry_delay_seconds)
        raise RuntimeError(
            "Gemini translation failed for "
            f"segment {segment_id} ({mode}) after "
            f"{attempt_count} attempt(s): {last_error}"
        ) from last_error

    def _build_http_options(self, types_module: Any) -> Any:
        return build_gemini_http_options(types_module, self.config.request_timeout_seconds)

    def _format_timeout(self) -> str:
        if self.config.request_timeout_seconds is None:
            return "none"
        return f"{self.config.request_timeout_seconds:g}s"

    def _extract_text_response(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        try:
            candidates = response.candidates
            parts = candidates[0].content.parts
            collected = [
                part.text.strip()
                for part in parts
                if getattr(part, "text", None) and part.text.strip()
            ]
        except (AttributeError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini translation response did not contain readable text") from exc
        return "\n".join(collected).strip()
