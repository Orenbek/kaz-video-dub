from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.providers.gemini_translate_provider import (
    GeminiTranslateConfig,
    GeminiTranslateProvider,
)


def test_default_translation_model_uses_gemini_flash_latest() -> None:
    assert GeminiTranslateConfig().model_name == "gemini-flash-latest"


def test_stub_kazakh_translation_sets_text_kk() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True))
    segments = [Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello there")]

    translated = provider.translate_to_kazakh(segments)

    assert translated[0].text_kk == "[kk stub] Hello there"
    assert translated[0].subtitle_zh is None


def test_stub_chinese_translation_sets_subtitle() -> None:
    provider = GeminiTranslateProvider(GeminiTranslateConfig(use_stub=True))
    segments = [Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello there")]

    translated = provider.translate_to_chinese_subtitles(segments)

    assert translated[0].subtitle_zh == "[zh stub] Hello there"
    assert translated[0].text_kk is None


def test_kazakh_prompt_includes_dubbing_length_guidance(tmp_path: Path) -> None:
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "translate_en_to_kk.txt"
    prompt_path.write_text(
        "Keep the source and Kazakh translation roughly similar in length.\n"
        "Avoid unnecessary expansion or added detail.\n"
        "Stay concise, especially for short segments.\n"
        "Make the wording speakable for dubbing.\n",
        encoding="utf-8",
    )

    prompt = prompt_path.read_text(encoding="utf-8")

    assert "roughly similar in length" in prompt
    assert "Avoid unnecessary expansion" in prompt
    assert "short segments" in prompt
    assert "speakable for dubbing" in prompt
