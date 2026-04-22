from pathlib import Path

import pytest

from video_dub.config import TTSAlignmentConfig
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.audio_compose import AudioComposeService
from video_dub.services.synthesis import classify_duration, compute_duration_ratio, summarize_duration_statuses


def test_compute_duration_ratio() -> None:
    assert compute_duration_ratio(2.0, 1.8) == 0.9
    assert compute_duration_ratio(0.0, 1.0) is None


def test_classify_duration_thresholds() -> None:
    alignment = TTSAlignmentConfig()

    assert classify_duration(target_duration=1.0, actual_duration=1.04, alignment=alignment) == "preferred"
    assert classify_duration(target_duration=1.0, actual_duration=1.12, alignment=alignment) == "acceptable"
    assert classify_duration(target_duration=1.0, actual_duration=0.8, alignment=alignment) == "too_short"
    assert classify_duration(target_duration=1.0, actual_duration=1.2, alignment=alignment) == "too_long"
    assert classify_duration(target_duration=1.0, actual_duration=1.4, alignment=alignment) == "manual_review"


def test_summarize_duration_statuses() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(id="1", start=0.0, end=1.0, text_en="a", duration_status="preferred"),
            Segment(id="2", start=1.0, end=2.0, text_en="b", duration_status="acceptable"),
            Segment(id="3", start=2.0, end=3.0, text_en="c", duration_status="too_long"),
            Segment(id="4", start=3.0, end=4.0, text_en="d", duration_status="manual_review"),
        ],
    )

    summary = summarize_duration_statuses(transcript)

    assert summary == {
        "total_segments": 4,
        "preferred_count": 1,
        "acceptable_count": 1,
        "flagged_count": 2,
        "manual_review_count": 1,
    }


def test_prepare_segment_adds_silence_padding_action() -> None:
    service = AudioComposeService(TTSAlignmentConfig(pad_with_silence=True))
    segment = Segment(
        id="1",
        start=0.0,
        end=1.0,
        text_en="a",
        tts_path=Path("seg.wav"),
        target_duration=1.0,
        tts_duration=0.7,
        correction_actions=[],
    )
    next_segment = Segment(id="2", start=1.5, end=2.0, text_en="b")

    prepared = service.prepare_segment(segment, next_segment)

    assert prepared.correction_actions == ["pad_silence"]
    assert prepared.duration_error_seconds == pytest.approx(-0.3)


def test_prepare_segment_keeps_status_when_trim_fixes_collision() -> None:
    service = AudioComposeService(TTSAlignmentConfig(allow_minor_overhang_seconds=0.1, manual_review_on_failure=True))
    service._trim_trailing_silence = lambda path, max_duration: max_duration
    segment = Segment(
        id="1",
        start=0.0,
        end=1.0,
        text_en="a",
        tts_path=Path("seg.wav"),
        target_duration=1.0,
        tts_duration=1.4,
        duration_status="too_long",
        correction_actions=[],
    )
    next_segment = Segment(id="2", start=1.0, end=2.0, text_en="b")

    prepared = service.prepare_segment(segment, next_segment)

    assert prepared.correction_actions == ["trim_trailing_silence"]
    assert prepared.duration_status == "too_long"
    assert prepared.tts_duration == pytest.approx(1.1)
