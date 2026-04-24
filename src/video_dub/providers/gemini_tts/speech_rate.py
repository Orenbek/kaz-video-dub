from __future__ import annotations

import re

CHINESE_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SLOW_WORDS_PER_SECOND = 1.6
BRISK_WORDS_PER_SECOND = 2.4
FAST_WORDS_PER_SECOND = 2.8
EXTREME_WORDS_PER_SECOND = 3.3
SLOW_CHINESE_CHARS_PER_SECOND = 3.0
BRISK_CHINESE_CHARS_PER_SECOND = 4.3
FAST_CHINESE_CHARS_PER_SECOND = 5.2
EXTREME_CHINESE_CHARS_PER_SECOND = 6.2
SHORT_SEGMENT_MAX_EXTREME_DURATION_SECONDS = 3.0


def is_chinese_language(language: str) -> bool:
    normalized = language.lower()
    return normalized.startswith("zh") or normalized in {"cn", "chinese"}


def count_speech_units(text: str, language: str) -> int:
    if is_chinese_language(language):
        return len(CHINESE_CHAR_PATTERN.findall(text))
    return len([token for token in text.split() if token.strip()])


def speech_unit_label(language: str) -> str:
    if is_chinese_language(language):
        return "Chinese characters"
    if language.lower().startswith("kk"):
        return "Kazakh words"
    return "words"


def speech_rate_thresholds(language: str) -> tuple[float, float, float, float]:
    if is_chinese_language(language):
        return (
            SLOW_CHINESE_CHARS_PER_SECOND,
            BRISK_CHINESE_CHARS_PER_SECOND,
            FAST_CHINESE_CHARS_PER_SECOND,
            EXTREME_CHINESE_CHARS_PER_SECOND,
        )
    return (
        SLOW_WORDS_PER_SECOND,
        BRISK_WORDS_PER_SECOND,
        FAST_WORDS_PER_SECOND,
        EXTREME_WORDS_PER_SECOND,
    )


def classify_speech_rate(
    *,
    rate: float,
    target_duration_seconds: float,
    language: str,
) -> str:
    slow_threshold, brisk_threshold, fast_threshold, extreme_threshold = speech_rate_thresholds(
        language
    )
    if rate < slow_threshold:
        return "slow"
    if (
        rate >= extreme_threshold
        and target_duration_seconds > SHORT_SEGMENT_MAX_EXTREME_DURATION_SECONDS
    ):
        return "extreme"
    if rate >= fast_threshold:
        return "fast"
    if rate >= brisk_threshold:
        return "brisk"
    return "normal"


def speech_rate_guidance(rate_category: str) -> str | None:
    if rate_category == "slow":
        return (
            "Pacing guidance: This is a low-density line. Speak calmly and naturally, "
            "but do not stretch syllables, add pauses, or add words."
        )
    if rate_category == "brisk":
        return (
            "Pacing guidance: This line needs a slightly brisk dubbing pace. Keep it "
            "compact and avoid long pauses."
        )
    if rate_category == "fast":
        return (
            "Pacing guidance: This is a fast dubbing line. Aim to fit the target "
            "duration with brisk, compact delivery while keeping pronunciation natural."
        )
    if rate_category == "extreme":
        return (
            "Pacing guidance: This line has extreme timing pressure. Use the fastest "
            "natural delivery, keep syllables crisp, and avoid drawn-out syllables, "
            "extra pauses, or added words."
        )
    return None


def build_segment_timing_notes(
    *,
    text: str,
    target_duration_seconds: float | None,
    language: str,
) -> str | None:
    if target_duration_seconds is None or target_duration_seconds <= 0:
        return None

    unit_count = count_speech_units(text, language)
    if unit_count <= 0:
        return None

    unit_label = speech_unit_label(language)
    rate = unit_count / target_duration_seconds
    rate_category = classify_speech_rate(
        rate=rate,
        target_duration_seconds=target_duration_seconds,
        language=language,
    )
    guidance = speech_rate_guidance(rate_category)
    if guidance is None:
        return None

    lines = [
        "### SEGMENT TIMING",
        f"Target duration: about {target_duration_seconds:.2f} seconds.",
        f"Text length: {unit_count} {unit_label}.",
        f"Estimated required pace: {rate:.2f} {unit_label}/second.",
        f"Pace category: {rate_category}.",
        guidance,
    ]
    return "\n".join(lines)
