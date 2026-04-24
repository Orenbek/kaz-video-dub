import wave
from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.providers.gemini_tts_provider import (
    DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE,
    GEMINI_TTS_VOICE_NAMES,
    GeminiTTSConfig,
    GeminiTTSProvider,
    build_segment_timing_notes,
    classify_speech_rate,
    count_speech_units,
)


def test_gemini_tts_voice_name_overrides_legacy_voice() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig(voice_name="Puck"))

    assert provider.resolve_voice_name("Kore") == "Puck"


def test_gemini_tts_voice_name_falls_back_to_legacy_voice() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig())

    assert provider.resolve_voice_name("Kore") == "Kore"


def test_gemini_tts_voice_names_include_documented_options() -> None:
    assert "Kore" in GEMINI_TTS_VOICE_NAMES
    assert "Sadaltager" in GEMINI_TTS_VOICE_NAMES


def test_gemini_tts_rejects_unknown_voice_name() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig())

    try:
        provider.validate_voice_name("UnknownVoice")
    except RuntimeError as exc:
        assert "Unsupported Gemini TTS voice_name" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unsupported Gemini TTS voice")


def test_gemini_tts_prompt_preamble_can_be_overridden() -> None:
    provider = GeminiTTSProvider(
        GeminiTTSConfig(prompt_preamble="Synthesize exactly.\n\n### TRANSCRIPT")
    )

    assert provider.build_tts_prompt("Сәлем") == "Synthesize exactly.\n\n### TRANSCRIPT\nСәлем"
    assert DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE != provider.config.prompt_preamble


def test_gemini_tts_prompt_omits_timing_notes_for_normal_pace() -> None:
    prompt = GeminiTTSProvider().build_tts_prompt(
        "Бұл қалыпты қысқа сөйлем.",
        target_duration_seconds=2.0,
        language="kk",
    )

    assert "### SEGMENT TIMING" not in prompt


def test_gemini_tts_prompt_injects_brisk_kazakh_timing_notes() -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig(language="kk"))

    prompt = provider.build_tts_prompt(
        "Бұл әлі де маңызды.",
        target_duration_seconds=1.5,
    )

    assert "### SEGMENT TIMING" in prompt
    assert "Text length: 4 Kazakh words." in prompt
    assert "Estimated required pace: 2.67 Kazakh words/second." in prompt
    assert "Pace category: brisk." in prompt
    assert "slightly brisk dubbing pace" in prompt
    assert prompt.index("### SEGMENT TIMING") < prompt.index("### TRANSCRIPT")


def test_gemini_tts_prompt_injects_fast_kazakh_timing_notes() -> None:
    prompt = GeminiTTSProvider(GeminiTTSConfig(language="kk")).build_tts_prompt(
        "Бұл әлі де өте маңызды.",
        target_duration_seconds=1.7,
    )

    assert "Pace category: fast." in prompt
    assert "fit the target duration" in prompt


def test_gemini_tts_prompt_injects_extreme_timing_notes() -> None:
    prompt = GeminiTTSProvider(GeminiTTSConfig(language="kk")).build_tts_prompt(
        "бір екі үш төрт бес алты жеті сегіз тоғыз он онбір онекі онүш онтөрт",
        target_duration_seconds=4.0,
    )

    assert "Pace category: extreme." in prompt
    assert "extreme timing pressure" in prompt


def test_gemini_tts_prompt_injects_slow_timing_notes() -> None:
    prompt = GeminiTTSProvider().build_tts_prompt(
        "Иә.",
        target_duration_seconds=2.0,
        language="kk",
    )

    assert "Text length: 1 Kazakh words." in prompt
    assert "Pace category: slow." in prompt
    assert "This is a low-density line" in prompt


def test_speech_rate_classifier_caps_short_segments_at_fast() -> None:
    assert (
        classify_speech_rate(
            rate=5.0,
            target_duration_seconds=1.0,
            language="kk",
        )
        == "fast"
    )


def test_speech_unit_count_uses_chinese_characters() -> None:
    assert count_speech_units("你好，NVIDIA！", "zh") == 2


def test_chinese_timing_notes_use_character_rate() -> None:
    notes = build_segment_timing_notes(
        text="这是一个用于验证长句极快语速分类的测试文本需要进入极限档位",
        target_duration_seconds=4.0,
        language="zh",
    )

    assert notes is not None
    assert "Chinese characters" in notes
    assert "Pace category: extreme." in notes


def test_stub_tts_writes_wav_file(tmp_path: Path) -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig(use_stub=True, sample_rate=24000))
    segment = Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello", text_kk="Сәлем")
    output_path = tmp_path / "seg_0001.wav"

    result = provider.synthesize_segment(segment, output_path, voice="kazakh-default")

    assert result.exists()
    with wave.open(str(result), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
