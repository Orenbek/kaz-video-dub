import wave
from pathlib import Path

import pytest

from video_dub.config import TTSAlignmentConfig
from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.audio_compose import AudioComposeService, TrimResult
from video_dub.services.synthesis import (
    MANUAL_REVIEW_PLACEHOLDER,
    SynthesisService,
    apply_time_stretch,
    can_apply_time_stretch,
    classify_duration_only,
    compute_duration_ratio,
    compute_max_safe_duration,
    compute_required_time_stretch_ratio,
    compute_required_time_stretch_ratio_for_collision,
    has_timeline_collision,
    materially_improves_duration,
    summarize_duration_statuses,
)


class DummyTTSProvider:
    def synthesize_segment(self, segment: Segment, output_path: Path, voice: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"{segment.id}:{voice}".encode("utf-8"))
        return output_path


def write_test_wav(path: Path, amplitudes: list[int], sample_rate: int = 1000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for amplitude in amplitudes:
            frames += int(amplitude).to_bytes(2, byteorder="little", signed=True)
        wav_file.writeframes(bytes(frames))


def test_compute_duration_ratio() -> None:
    assert compute_duration_ratio(2.0, 1.8) == 0.9
    assert compute_duration_ratio(0.0, 1.0) is None


def test_classify_duration_only_thresholds() -> None:
    alignment = TTSAlignmentConfig()

    assert (
        classify_duration_only(target_duration=1.0, actual_duration=1.04, alignment=alignment)
        == "preferred"
    )
    assert (
        classify_duration_only(target_duration=1.0, actual_duration=1.12, alignment=alignment)
        == "acceptable"
    )
    assert (
        classify_duration_only(target_duration=1.0, actual_duration=0.8, alignment=alignment)
        == "too_short"
    )
    assert (
        classify_duration_only(target_duration=1.0, actual_duration=1.2, alignment=alignment)
        == "too_long"
    )


def test_compute_max_safe_duration_and_collision() -> None:
    alignment = TTSAlignmentConfig(allow_minor_overhang_seconds=0.1)
    segment = Segment(id="1", start=0.0, end=1.0, text_en="a")
    next_segment = Segment(id="2", start=1.0, end=2.0, text_en="b")

    assert compute_max_safe_duration(segment, next_segment, alignment) == pytest.approx(1.1)
    assert has_timeline_collision(segment, next_segment, 1.05, alignment) is False
    assert has_timeline_collision(segment, next_segment, 1.11, alignment) is True


def test_time_stretch_guardrails() -> None:
    alignment = TTSAlignmentConfig(enable_time_stretch=True, max_time_stretch_ratio=0.08)

    assert compute_required_time_stretch_ratio(1.0, 1.2) == pytest.approx(0.8333333333)
    assert can_apply_time_stretch(0.95, alignment) is True
    assert can_apply_time_stretch(0.8, alignment) is False


def test_collision_ratio_targets_safe_end() -> None:
    alignment = TTSAlignmentConfig(allow_minor_overhang_seconds=0.1)
    segment = Segment(id="1", start=0.0, end=1.0, text_en="a")
    next_segment = Segment(id="2", start=1.0, end=2.0, text_en="b")

    ratio = compute_required_time_stretch_ratio_for_collision(segment, next_segment, 1.4, alignment)

    assert ratio == pytest.approx(1.1 / 1.4)


def test_materially_improves_duration_requires_clear_gain() -> None:
    alignment = TTSAlignmentConfig(min_time_stretch_improvement_seconds=0.05)

    assert (
        materially_improves_duration(
            target_duration=1.0,
            current_duration=1.2,
            candidate_duration=1.12,
            alignment=alignment,
        )
        is True
    )
    assert (
        materially_improves_duration(
            target_duration=1.0,
            current_duration=1.2,
            candidate_duration=1.16,
            alignment=alignment,
        )
        is False
    )


def test_summarize_duration_statuses() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="1",
                start=0.0,
                end=1.0,
                text_en="a",
                duration_status="preferred",
                duration_error_seconds=0.01,
            ),
            Segment(
                id="2",
                start=1.0,
                end=2.0,
                text_en="b",
                duration_status="acceptable",
                duration_error_seconds=0.04,
                correction_actions=["pad_silence"],
            ),
            Segment(
                id="3",
                start=2.0,
                end=3.0,
                text_en="c",
                duration_status="too_long",
                duration_error_seconds=0.2,
                correction_actions=["time_stretch"],
            ),
            Segment(
                id="4",
                start=3.0,
                end=4.0,
                text_en="d",
                duration_status="manual_review",
                duration_error_seconds=0.3,
                correction_actions=["trim_trailing_silence"],
            ),
        ],
    )

    summary = summarize_duration_statuses(transcript)

    assert summary == {
        "total_segments": 4,
        "preferred_count": 1,
        "acceptable_count": 1,
        "too_short_count": 0,
        "too_long_count": 1,
        "manual_review_count": 1,
        "avg_abs_duration_error": pytest.approx((0.01 + 0.04 + 0.2 + 0.3) / 4),
        "time_stretch_applied_count": 1,
        "trim_trailing_silence_applied_count": 1,
        "pad_silence_applied_count": 1,
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
        duration_status=MANUAL_REVIEW_PLACEHOLDER,
    )
    next_segment = Segment(id="2", start=1.5, end=2.0, text_en="b")

    prepared = service.prepare_segment(segment, next_segment)

    assert prepared.correction_actions == ["pad_silence"]
    assert prepared.duration_status == "too_short"
    assert prepared.duration_error_seconds == pytest.approx(-0.3)
    assert prepared.has_timeline_collision is False


def test_prepare_segment_keeps_status_when_trim_fixes_collision() -> None:
    service = AudioComposeService(
        TTSAlignmentConfig(allow_minor_overhang_seconds=0.1, manual_review_on_failure=True)
    )
    service._trim_trailing_silence = lambda path, max_duration: TrimResult(
        applied=True,
        output_path=path,
        duration=max_duration,
    )
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
        has_timeline_collision=True,
    )
    next_segment = Segment(id="2", start=1.0, end=2.0, text_en="b")

    prepared = service.prepare_segment(segment, next_segment)

    assert prepared.correction_actions == ["trim_trailing_silence"]
    assert prepared.duration_status == "too_long"
    assert prepared.tts_duration == pytest.approx(1.1)
    assert prepared.has_timeline_collision is False


def test_prepare_segment_marks_manual_review_when_collision_remains() -> None:
    service = AudioComposeService(
        TTSAlignmentConfig(allow_minor_overhang_seconds=0.1, manual_review_on_failure=True)
    )
    service._trim_trailing_silence = lambda path, max_duration: TrimResult(
        applied=False,
        output_path=path,
        duration=1.3,
    )
    segment = Segment(
        id="1",
        start=0.0,
        end=1.0,
        text_en="a",
        tts_path=Path("seg.wav"),
        target_duration=1.0,
        tts_duration=1.4,
        duration_status=MANUAL_REVIEW_PLACEHOLDER,
        correction_actions=[],
    )
    next_segment = Segment(id="2", start=1.0, end=2.0, text_en="b")

    prepared = service.prepare_segment(segment, next_segment)

    assert prepared.duration_status == "manual_review"
    assert prepared.has_timeline_collision is True


def test_trim_trailing_silence_only_removes_detected_silence(tmp_path: Path) -> None:
    service = AudioComposeService(
        TTSAlignmentConfig(trim_trailing_silence=True, max_trailing_silence_trim_seconds=0.3)
    )
    wav_path = tmp_path / "seg.wav"
    write_test_wav(wav_path, [1000] * 700 + [0] * 200 + [0] * 100)

    result = service._trim_trailing_silence(wav_path, max_duration=0.85)

    assert result.applied is True
    assert result.output_path.name == "seg.trimmed.wav"
    assert result.duration == pytest.approx(0.85, abs=0.02)


def test_trim_trailing_silence_does_not_trim_voiced_tail(tmp_path: Path) -> None:
    service = AudioComposeService(
        TTSAlignmentConfig(trim_trailing_silence=True, max_trailing_silence_trim_seconds=0.3)
    )
    wav_path = tmp_path / "seg.wav"
    write_test_wav(wav_path, [1000] * 700 + [0] * 100 + [900] * 200)

    result = service._trim_trailing_silence(wav_path, max_duration=0.85)

    assert result.applied is False
    assert result.output_path == wav_path
    assert result.duration == pytest.approx(1.0, abs=0.02)


def test_apply_time_stretch_changes_real_wav_duration(tmp_path: Path) -> None:
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "output.wav"
    write_test_wav(input_path, [1200] * 1000, sample_rate=1000)

    apply_time_stretch(input_path, output_path, ratio=0.9)

    with wave.open(str(output_path), "rb") as wav_file:
        stretched_duration = wav_file.getnframes() / wav_file.getframerate()

    original_duration = 1.0
    assert output_path.exists()
    assert stretched_duration == pytest.approx(0.9, abs=0.08)
    assert stretched_duration < original_duration


def test_audio_compose_compose_applies_delay_and_padding_with_real_wavs(tmp_path: Path) -> None:
    first_wav = tmp_path / "seg1.wav"
    second_wav = tmp_path / "seg2.wav"
    output_wav = tmp_path / "dub.wav"

    write_test_wav(first_wav, [1000] * 300, sample_rate=1000)
    write_test_wav(second_wav, [1000] * 200, sample_rate=1000)

    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg1",
                start=0.0,
                end=0.5,
                text_en="a",
                text_kk="aa",
                tts_path=first_wav,
                target_duration=0.5,
                tts_duration=0.3,
            ),
            Segment(
                id="seg2",
                start=0.8,
                end=1.0,
                text_en="b",
                text_kk="bb",
                tts_path=second_wav,
                target_duration=0.2,
                tts_duration=0.2,
            ),
        ],
    )

    service = AudioComposeService(TTSAlignmentConfig())
    service.compose(transcript, output_wav)

    duration = probe_duration(output_wav)

    assert output_wav.exists()
    assert duration == pytest.approx(1.0, abs=0.08)


def test_synthesis_service_leaves_acceptable_non_collision_segment_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(DummyTTSProvider(), TTSAlignmentConfig())
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg1", start=0.0, end=1.0, text_en="a", text_kk="aa")],
    )

    monkeypatch.setattr("video_dub.services.synthesis.measure_wav_duration", lambda path: 1.12)

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.duration_status == "acceptable"
    assert segment.correction_actions == []
    assert segment.time_stretch_ratio is None
    assert segment.has_timeline_collision is False
    assert segment.raw_tts_path == tmp_path / "tts_raw" / "seg1.wav"
    assert segment.tts_path == tmp_path / "tts" / "seg1.wav"
    assert segment.tts_path is not None
    assert segment.tts_path.exists()


def test_synthesis_service_uses_collision_first_bounded_compression(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(
        DummyTTSProvider(),
        TTSAlignmentConfig(
            enable_time_stretch=True, max_time_stretch_ratio=0.08, allow_minor_overhang_seconds=0.1
        ),
    )
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(id="seg1", start=0.0, end=1.4, text_en="a", text_kk="aa"),
            Segment(id="seg2", start=1.0, end=2.0, text_en="b", text_kk="bb"),
        ],
    )

    durations = {
        str(tmp_path / "tts_raw" / "seg1.wav"): 1.16,
        str(tmp_path / "tts" / "seg1.wav"): 1.08,
        str(tmp_path / "tts_raw" / "seg2.wav"): 0.9,
        str(tmp_path / "tts" / "seg2.wav"): 0.9,
    }

    monkeypatch.setattr(
        "video_dub.services.synthesis.measure_wav_duration", lambda path: durations[str(path)]
    )

    def fake_apply(input_path: Path, output_path: Path, ratio: float) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"stretch:{ratio}".encode("utf-8"))
        return output_path

    monkeypatch.setattr("video_dub.services.synthesis.apply_time_stretch", fake_apply)

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.correction_actions == ["time_stretch"]
    assert segment.time_stretch_ratio == pytest.approx(1.1 / 1.16)
    assert segment.tts_duration == pytest.approx(1.08)
    assert segment.duration_status == "too_short"
    assert segment.has_timeline_collision is False


def test_synthesis_service_keeps_non_collision_preferred_segment_without_stretch(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(
        DummyTTSProvider(),
        TTSAlignmentConfig(
            enable_time_stretch=True,
            max_time_stretch_ratio=0.08,
            min_time_stretch_improvement_seconds=0.05,
        ),
    )
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg1", start=0.0, end=1.0, text_en="a", text_kk="aa")],
    )

    durations = {
        str(tmp_path / "tts_raw" / "seg1.wav"): 0.92,
        str(tmp_path / "tts" / "seg1.wav"): 1.0,
    }
    monkeypatch.setattr(
        "video_dub.services.synthesis.measure_wav_duration", lambda path: durations[str(path)]
    )
    monkeypatch.setattr(
        "video_dub.services.synthesis.apply_time_stretch",
        lambda input_path, output_path, ratio: output_path.write_bytes(b"stretch") or output_path,
    )

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.correction_actions == []
    assert segment.duration_status == "preferred"
    assert segment.time_stretch_ratio is None


def test_synthesis_service_keeps_unresolved_collision_as_placeholder_for_compose(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(
        DummyTTSProvider(),
        TTSAlignmentConfig(
            enable_time_stretch=True, max_time_stretch_ratio=0.08, allow_minor_overhang_seconds=0.1
        ),
    )
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(id="seg1", start=0.0, end=1.0, text_en="a", text_kk="aa"),
            Segment(id="seg2", start=1.0, end=2.0, text_en="b", text_kk="bb"),
        ],
    )

    monkeypatch.setattr("video_dub.services.synthesis.measure_wav_duration", lambda path: 1.4)

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.duration_status == MANUAL_REVIEW_PLACEHOLDER
    assert segment.has_timeline_collision is True
    assert segment.correction_actions == []


def test_synthesis_service_marks_zero_duration_segment_for_manual_review(tmp_path: Path) -> None:
    service = SynthesisService(DummyTTSProvider(), TTSAlignmentConfig())
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg0", start=1.0, end=1.0, text_en="a", text_kk="aa")],
    )

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.target_duration == 0.0
    assert segment.duration_status == "manual_review"
    assert segment.duration_error_seconds is None
    assert segment.time_stretch_ratio is None
    assert segment.has_timeline_collision is None


def test_synthesis_service_last_segment_never_has_timeline_collision(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(
        DummyTTSProvider(),
        TTSAlignmentConfig(enable_time_stretch=True, allow_minor_overhang_seconds=0.1),
    )
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="last", start=0.0, end=1.0, text_en="a", text_kk="aa")],
    )

    monkeypatch.setattr("video_dub.services.synthesis.measure_wav_duration", lambda path: 1.6)

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert segment.has_timeline_collision is False
    assert segment.duration_status == "too_long"


def test_synthesis_service_skips_non_collision_stretch_when_required_ratio_exceeds_limit(
    tmp_path: Path, monkeypatch
) -> None:
    service = SynthesisService(
        DummyTTSProvider(),
        TTSAlignmentConfig(enable_time_stretch=True, max_time_stretch_ratio=0.08),
    )
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg1", start=0.0, end=1.0, text_en="a", text_kk="aa")],
    )

    monkeypatch.setattr("video_dub.services.synthesis.measure_wav_duration", lambda path: 1.2)

    apply_called = False

    def fake_apply(input_path: Path, output_path: Path, ratio: float) -> Path:
        nonlocal apply_called
        apply_called = True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"stretch")
        return output_path

    monkeypatch.setattr("video_dub.services.synthesis.apply_time_stretch", fake_apply)

    result = service.run(
        transcript, tts_dir=tmp_path / "tts", raw_tts_dir=tmp_path / "tts_raw", voice="Kore"
    )

    segment = result.segments[0]
    assert apply_called is False
    assert segment.correction_actions == []
    assert segment.time_stretch_ratio is None
    assert segment.duration_status == "too_long"


def test_synthesis_service_skips_duration_control_when_disabled(tmp_path: Path) -> None:
    service = SynthesisService(DummyTTSProvider(), TTSAlignmentConfig(enabled=False))
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg1", start=0.0, end=1.0, text_en="a", text_kk="aa")],
    )

    result = service.run(
        transcript,
        tts_dir=tmp_path / "tts",
        raw_tts_dir=tmp_path / "tts_raw",
        voice="Kore",
    )

    segment = result.segments[0]
    assert segment.tts_path == tmp_path / "tts" / "seg1.wav"
    assert segment.raw_tts_path == tmp_path / "tts" / "seg1.wav"
    assert segment.duration_status is None
    assert segment.tts_duration is None
    assert segment.has_timeline_collision is None


def test_audio_compose_prepare_transcript_is_passthrough_when_disabled() -> None:
    service = AudioComposeService(TTSAlignmentConfig(enabled=False))
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg1",
                start=0.0,
                end=1.0,
                text_en="a",
                text_kk="aa",
                duration_status="too_long",
                correction_actions=["time_stretch"],
            )
        ],
    )

    prepared = service.prepare_transcript(transcript)

    assert prepared == transcript
