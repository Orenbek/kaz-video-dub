from __future__ import annotations

from video_dub.providers.gemini_tts.prompts import (
    DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE,
    build_tts_prompt,
    insert_timing_notes_before_transcript,
)
from video_dub.providers.gemini_tts.provider import GeminiTTSConfig, GeminiTTSProvider
from video_dub.providers.gemini_tts.speech_rate import (
    BRISK_CHINESE_CHARS_PER_SECOND,
    BRISK_WORDS_PER_SECOND,
    EXTREME_CHINESE_CHARS_PER_SECOND,
    EXTREME_WORDS_PER_SECOND,
    FAST_CHINESE_CHARS_PER_SECOND,
    FAST_WORDS_PER_SECOND,
    SHORT_SEGMENT_MAX_EXTREME_DURATION_SECONDS,
    SLOW_CHINESE_CHARS_PER_SECOND,
    SLOW_WORDS_PER_SECOND,
    build_segment_timing_notes,
    classify_speech_rate,
    count_speech_units,
    is_chinese_language,
    speech_rate_guidance,
    speech_rate_thresholds,
    speech_unit_label,
)
from video_dub.providers.gemini_tts.voices import GEMINI_TTS_VOICE_NAMES, validate_voice_name

__all__ = [
    "BRISK_CHINESE_CHARS_PER_SECOND",
    "BRISK_WORDS_PER_SECOND",
    "DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE",
    "EXTREME_CHINESE_CHARS_PER_SECOND",
    "EXTREME_WORDS_PER_SECOND",
    "FAST_CHINESE_CHARS_PER_SECOND",
    "FAST_WORDS_PER_SECOND",
    "GEMINI_TTS_VOICE_NAMES",
    "GeminiTTSConfig",
    "GeminiTTSProvider",
    "SHORT_SEGMENT_MAX_EXTREME_DURATION_SECONDS",
    "SLOW_CHINESE_CHARS_PER_SECOND",
    "SLOW_WORDS_PER_SECOND",
    "build_segment_timing_notes",
    "build_tts_prompt",
    "classify_speech_rate",
    "count_speech_units",
    "insert_timing_notes_before_transcript",
    "is_chinese_language",
    "speech_rate_guidance",
    "speech_rate_thresholds",
    "speech_unit_label",
    "validate_voice_name",
]
