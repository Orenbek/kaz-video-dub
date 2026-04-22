from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


def test_segment_duration() -> None:
    segment = Segment(id="seg_0001", start=1.5, end=4.0, text_en="hello")
    assert segment.duration == 2.5


def test_segment_stores_duration_control_metadata() -> None:
    segment = Segment(
        id="seg_0001",
        start=0.0,
        end=1.0,
        text_en="Hello",
        text_kk="Сәлем",
        tts_path=Path("artifacts/tts/seg_0001.wav"),
        target_duration=1.0,
        initial_tts_duration=0.82,
        tts_duration=0.82,
        duration_status="acceptable",
        duration_error_seconds=-0.18,
        correction_actions=["pad_silence"],
        time_stretch_ratio=None,
    )

    transcript = TranscriptDocument(source_audio_path=Path("source.wav"), language="en", segments=[segment])

    stored = transcript.segments[0]
    assert stored.target_duration == 1.0
    assert stored.initial_tts_duration == 0.82
    assert stored.tts_duration == 0.82
    assert stored.duration_status == "acceptable"
    assert stored.duration_error_seconds == -0.18
    assert stored.correction_actions == ["pad_silence"]
    assert stored.time_stretch_ratio is None
