from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from video_dub.models.segment import Segment

TranslationMode = Literal["kk", "zh"]


class GeminiContentGenerator(Protocol):
    def generate_content(self, *, model: str, contents: str) -> Any: ...


class GeminiClientLike(Protocol):
    @property
    def models(self) -> GeminiContentGenerator: ...


class GeminiTranslateConfig(BaseModel):
    model_name: str = "gemini-2.5-pro"
    api_key_env: str = "GEMINI_API_KEY"
    use_stub: bool = True
    prompt_dir: Path = Path("configs/prompts")
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class GeminiTranslateProvider:
    def __init__(self, config: GeminiTranslateConfig | None = None) -> None:
        self.config = config or GeminiTranslateConfig()

    def translate_to_kazakh(self, segments: list[Segment]) -> list[Segment]:
        if self.config.use_stub:
            return [segment.model_copy(update={"text_kk": self._stub_translate(segment.text_en, "kk")}) for segment in segments]
        return self._translate_with_gemini(segments, mode="kk")

    def translate_to_chinese_subtitles(self, segments: list[Segment]) -> list[Segment]:
        if self.config.use_stub:
            return [segment.model_copy(update={"subtitle_zh": self._stub_translate(segment.text_en, "zh")}) for segment in segments]
        return self._translate_with_gemini(segments, mode="zh")

    def _translate_with_gemini(self, segments: list[Segment], mode: TranslationMode) -> list[Segment]:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing {self.config.api_key_env} for Gemini translation")

        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc

        prompt_name = "translate_en_to_kk.txt" if mode == "kk" else "translate_en_to_zh_subtitle.txt"
        system_prompt = (self.config.prompt_dir / prompt_name).read_text(encoding="utf-8")
        client = genai.Client(api_key=api_key)

        translated_segments: list[Segment] = []
        for segment in segments:
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
        for attempt in range(1, self.config.max_retries + 1):
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
                if attempt == self.config.max_retries:
                    break
                time.sleep(self.config.retry_delay_seconds)
        raise RuntimeError(
            f"Gemini translation failed for segment {segment_id} ({mode}) after {self.config.max_retries} attempts: {last_error}"
        ) from last_error

    def _extract_text_response(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        try:
            candidates = response.candidates
            parts = candidates[0].content.parts
            collected = [part.text.strip() for part in parts if getattr(part, "text", None) and part.text.strip()]
        except (AttributeError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini translation response did not contain readable text") from exc
        return "\n".join(collected).strip()

    def _stub_translate(self, text: str, mode: TranslationMode) -> str:
        prefix = "[kk stub]" if mode == "kk" else "[zh stub]"
        return f"{prefix} {text.strip()}"
