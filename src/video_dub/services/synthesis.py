from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Protocol

from video_dub.config import TTSAlignmentConfig
from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument

MANUAL_REVIEW_PLACEHOLDER = "manual_review_placeholder"


class TTSProvider(Protocol):
    def synthesize_segment(self, segment: Segment, output_path: Path, voice: str) -> Path: ...


def measure_wav_duration(path: Path) -> float:
    return probe_duration(path)


def compute_target_duration(segment: Segment) -> float:
    return max(0.0, segment.end - segment.start)


def format_optional_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def resolve_segment_voice(
    segment: Segment,
    default_voice: str,
    voices_by_speaker: Mapping[str, str] | None = None,
) -> str:
    if segment.speaker and voices_by_speaker and segment.speaker in voices_by_speaker:
        return voices_by_speaker[segment.speaker]
    return default_voice


def compute_duration_ratio(target_duration: float, actual_duration: float) -> float | None:
    if target_duration <= 0:
        return None
    return actual_duration / target_duration


def compute_duration_error(target_duration: float, actual_duration: float) -> float | None:
    if target_duration <= 0:
        return None
    return actual_duration - target_duration


def compute_max_safe_duration(
    segment: Segment,
    next_segment: Segment | None,
    alignment: TTSAlignmentConfig,
) -> float | None:
    if next_segment is None:
        return None
    return max(0.0, next_segment.start + alignment.allow_minor_overhang_seconds - segment.start)


def has_timeline_collision(
    segment: Segment,
    next_segment: Segment | None,
    actual_duration: float,
    alignment: TTSAlignmentConfig,
) -> bool:
    max_safe_duration = compute_max_safe_duration(segment, next_segment, alignment)
    if max_safe_duration is None:
        return False
    return actual_duration > max_safe_duration


def classify_duration_only(
    *,
    target_duration: float,
    actual_duration: float,
    alignment: TTSAlignmentConfig,
) -> str:
    ratio = compute_duration_ratio(target_duration, actual_duration)
    if ratio is None:
        return "manual_review"

    preferred_min = 1.0 - alignment.preferred_ratio_tolerance
    preferred_max = 1.0 + alignment.preferred_ratio_tolerance
    acceptable_min = 1.0 - alignment.max_ratio_tolerance
    acceptable_max = 1.0 + alignment.max_ratio_tolerance

    if preferred_min <= ratio <= preferred_max:
        return "preferred"
    if acceptable_min <= ratio <= acceptable_max:
        return "acceptable"
    if ratio < acceptable_min:
        return "too_short"
    if ratio > acceptable_max:
        return "too_long"
    return "manual_review"


def compute_required_time_stretch_ratio(
    target_duration: float, actual_duration: float
) -> float | None:
    if target_duration <= 0 or actual_duration <= 0:
        return None
    return target_duration / actual_duration


def compute_required_time_stretch_ratio_for_collision(
    segment: Segment,
    next_segment: Segment | None,
    actual_duration: float,
    alignment: TTSAlignmentConfig,
) -> float | None:
    max_safe_duration = compute_max_safe_duration(segment, next_segment, alignment)
    if max_safe_duration is None or actual_duration <= 0 or actual_duration <= max_safe_duration:
        return None
    return max_safe_duration / actual_duration


def can_apply_time_stretch(required_ratio: float | None, alignment: TTSAlignmentConfig) -> bool:
    if not alignment.enable_time_stretch or required_ratio is None or required_ratio <= 0:
        return False
    return abs(1.0 - required_ratio) <= alignment.max_time_stretch_ratio


def materially_improves_duration(
    *,
    target_duration: float,
    current_duration: float,
    candidate_duration: float,
    alignment: TTSAlignmentConfig,
) -> bool:
    current_error = abs(compute_duration_error(target_duration, current_duration) or 0.0)
    candidate_error = abs(compute_duration_error(target_duration, candidate_duration) or 0.0)
    if candidate_error >= current_error:
        return False
    return (current_error - candidate_error) >= alignment.min_time_stretch_improvement_seconds


def apply_time_stretch(input_path: Path, output_path: Path, ratio: float) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atempo = 1.0 / ratio
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-filter:a",
        f"atempo={atempo:.6f}",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True)
    return output_path


def summarize_duration_statuses(transcript: TranscriptDocument) -> dict[str, int | float]:
    summary: dict[str, int | float] = {
        "total_segments": len(transcript.segments),
        "preferred_count": 0,
        "acceptable_count": 0,
        "too_short_count": 0,
        "too_long_count": 0,
        "manual_review_count": 0,
        "avg_abs_duration_error": 0.0,
        "time_stretch_applied_count": 0,
        "trim_trailing_silence_applied_count": 0,
        "pad_silence_applied_count": 0,
    }
    total_abs_error = 0.0
    measured_segments = 0

    for segment in transcript.segments:
        if segment.duration_status == "preferred":
            summary["preferred_count"] += 1
        elif segment.duration_status == "acceptable":
            summary["acceptable_count"] += 1
        elif segment.duration_status == "too_short":
            summary["too_short_count"] += 1
        elif segment.duration_status == "too_long":
            summary["too_long_count"] += 1
        elif segment.duration_status == "manual_review":
            summary["manual_review_count"] += 1

        if segment.duration_error_seconds is not None:
            total_abs_error += abs(segment.duration_error_seconds)
            measured_segments += 1

        summary["time_stretch_applied_count"] += int("time_stretch" in segment.correction_actions)
        summary["trim_trailing_silence_applied_count"] += int(
            "trim_trailing_silence" in segment.correction_actions
        )
        summary["pad_silence_applied_count"] += int("pad_silence" in segment.correction_actions)

    if measured_segments:
        summary["avg_abs_duration_error"] = total_abs_error / measured_segments
    return summary


class SynthesisService:
    def __init__(self, provider: TTSProvider, alignment: TTSAlignmentConfig) -> None:
        self.provider = provider
        self.alignment = alignment

    def run(
        self,
        transcript: TranscriptDocument,
        tts_dir: Path,
        voice: str,
        raw_tts_dir: Path | None = None,
        voices_by_speaker: Mapping[str, str] | None = None,
    ) -> TranscriptDocument:
        total_segments = len(transcript.segments)
        if not self.alignment.enabled:
            print(f"[tts] Alignment disabled; synthesizing {total_segments} segments")
            passthrough_segments = []
            for index, segment in enumerate(transcript.segments, start=1):
                segment_voice = resolve_segment_voice(segment, voice, voices_by_speaker)
                print(
                    f"[tts] Synthesizing {index}/{total_segments} {segment.id} "
                    f"speaker={segment.speaker or 'unknown'} voice={segment_voice}"
                )
                output_path = tts_dir / f"{segment.id}.wav"
                self.provider.synthesize_segment(segment, output_path, segment_voice)
                passthrough_segments.append(
                    segment.model_copy(
                        update={
                            "tts_path": output_path,
                            "raw_tts_path": output_path,
                            "tts_duration": None,
                            "target_duration": None,
                            "initial_tts_duration": None,
                            "duration_status": None,
                            "duration_error_seconds": None,
                            "correction_actions": [],
                            "time_stretch_ratio": None,
                            "has_timeline_collision": None,
                        }
                    )
                )
            return transcript.model_copy(update={"segments": passthrough_segments})

        print(f"[tts] Starting synthesis with duration alignment: segments={total_segments}")
        raw_dir = raw_tts_dir or tts_dir
        synthesized_segments = []
        for index, segment in enumerate(transcript.segments):
            next_segment = (
                transcript.segments[index + 1] if index + 1 < len(transcript.segments) else None
            )
            segment_voice = resolve_segment_voice(segment, voice, voices_by_speaker)
            print(
                f"[tts] Synthesizing {index + 1}/{total_segments} {segment.id} "
                f"speaker={segment.speaker or 'unknown'} voice={segment_voice}"
            )
            processed_segment = self.process_segment(
                segment=segment,
                next_segment=next_segment,
                tts_dir=tts_dir,
                raw_tts_dir=raw_dir,
                voice=segment_voice,
            )
            actions = ",".join(processed_segment.correction_actions) or "none"
            print(
                f"[tts] Finished {segment.id}: "
                f"target={format_optional_seconds(processed_segment.target_duration)} "
                f"raw={format_optional_seconds(processed_segment.initial_tts_duration)} "
                f"final={format_optional_seconds(processed_segment.tts_duration)} "
                f"status={processed_segment.duration_status} actions={actions}"
            )
            synthesized_segments.append(processed_segment)
        return transcript.model_copy(update={"segments": synthesized_segments})

    def process_segment(
        self,
        *,
        segment: Segment,
        next_segment: Segment | None,
        tts_dir: Path,
        raw_tts_dir: Path,
        voice: str,
    ) -> Segment:
        target_duration = compute_target_duration(segment)
        if target_duration <= 0:
            return segment.model_copy(
                update={
                    "target_duration": target_duration,
                    "duration_status": "manual_review",
                    "duration_error_seconds": None,
                    "correction_actions": [],
                    "time_stretch_ratio": None,
                    "has_timeline_collision": None,
                }
            )

        raw_path = raw_tts_dir / f"{segment.id}.wav"
        final_path = tts_dir / f"{segment.id}.wav"
        self.provider.synthesize_segment(segment, raw_path, voice)
        raw_duration = measure_wav_duration(raw_path)
        raw_collision = has_timeline_collision(segment, next_segment, raw_duration, self.alignment)
        raw_status = classify_duration_only(
            target_duration=target_duration,
            actual_duration=raw_duration,
            alignment=self.alignment,
        )

        chosen_path = raw_path
        chosen_duration = raw_duration
        correction_actions: list[str] = []
        time_stretch_ratio: float | None = None

        if raw_collision:
            required_ratio = compute_required_time_stretch_ratio_for_collision(
                segment,
                next_segment,
                raw_duration,
                self.alignment,
            )
            if (
                can_apply_time_stretch(required_ratio, self.alignment)
                and required_ratio is not None
                and required_ratio < 1.0
            ):
                candidate_path = final_path
                apply_time_stretch(raw_path, candidate_path, required_ratio)
                candidate_duration = measure_wav_duration(candidate_path)
                if not has_timeline_collision(
                    segment, next_segment, candidate_duration, self.alignment
                ):
                    chosen_path = candidate_path
                    chosen_duration = candidate_duration
                    correction_actions.append("time_stretch")
                    time_stretch_ratio = required_ratio
        elif raw_status in {"too_short", "too_long"}:
            required_ratio = compute_required_time_stretch_ratio(target_duration, raw_duration)
            if (
                can_apply_time_stretch(required_ratio, self.alignment)
                and required_ratio is not None
            ):
                candidate_path = final_path
                apply_time_stretch(raw_path, candidate_path, required_ratio)
                candidate_duration = measure_wav_duration(candidate_path)
                candidate_status = classify_duration_only(
                    target_duration=target_duration,
                    actual_duration=candidate_duration,
                    alignment=self.alignment,
                )
                if candidate_status in {"preferred", "acceptable"} and materially_improves_duration(
                    target_duration=target_duration,
                    current_duration=raw_duration,
                    candidate_duration=candidate_duration,
                    alignment=self.alignment,
                ):
                    chosen_path = candidate_path
                    chosen_duration = candidate_duration
                    correction_actions.append("time_stretch")
                    time_stretch_ratio = required_ratio

        if chosen_path == raw_path:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw_path, final_path)
            chosen_path = final_path

        final_collision = has_timeline_collision(
            segment, next_segment, chosen_duration, self.alignment
        )
        if final_collision:
            final_status = MANUAL_REVIEW_PLACEHOLDER
        else:
            final_status = classify_duration_only(
                target_duration=target_duration,
                actual_duration=chosen_duration,
                alignment=self.alignment,
            )

        return segment.model_copy(
            update={
                "raw_tts_path": raw_path,
                "tts_path": chosen_path,
                "target_duration": target_duration,
                "initial_tts_duration": raw_duration,
                "tts_duration": chosen_duration,
                "duration_status": final_status,
                "duration_error_seconds": compute_duration_error(target_duration, chosen_duration),
                "correction_actions": correction_actions,
                "time_stretch_ratio": time_stretch_ratio,
                "has_timeline_collision": final_collision,
            }
        )
