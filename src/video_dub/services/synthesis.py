from __future__ import annotations

from pathlib import Path

from video_dub.config import TTSAlignmentConfig
from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_tts_provider import GeminiTTSProvider


def measure_wav_duration(path: Path) -> float:
    return probe_duration(path)


def compute_duration_ratio(target_duration: float, actual_duration: float) -> float | None:
    if target_duration <= 0:
        return None
    return actual_duration / target_duration


def classify_duration(
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
    if ratio < alignment.short_ratio:
        return "too_short"
    if ratio > alignment.severe_long_ratio:
        return "manual_review" if alignment.manual_review_on_failure else "too_long"
    if ratio > acceptable_max:
        return "too_long"
    return "manual_review"


def summarize_duration_statuses(transcript: TranscriptDocument) -> dict[str, int]:
    summary = {
        "total_segments": len(transcript.segments),
        "preferred_count": 0,
        "acceptable_count": 0,
        "flagged_count": 0,
        "manual_review_count": 0,
    }
    for segment in transcript.segments:
        if segment.duration_status == "preferred":
            summary["preferred_count"] += 1
        elif segment.duration_status == "acceptable":
            summary["acceptable_count"] += 1
        else:
            summary["flagged_count"] += 1
            if segment.duration_status == "manual_review":
                summary["manual_review_count"] += 1
    return summary


class SynthesisService:
    def __init__(self, provider: GeminiTTSProvider, alignment: TTSAlignmentConfig) -> None:
        self.provider = provider
        self.alignment = alignment

    def run(self, transcript: TranscriptDocument, tts_dir: Path, voice: str) -> TranscriptDocument:
        synthesized_segments = []
        for segment in transcript.segments:
            output_path = tts_dir / f"{segment.id}.wav"
            self.provider.synthesize_segment(segment, output_path, voice)
            duration = measure_wav_duration(output_path)
            target_duration = segment.duration
            duration_status = classify_duration(
                target_duration=target_duration,
                actual_duration=duration,
                alignment=self.alignment,
            )
            synthesized_segments.append(
                segment.model_copy(
                    update={
                        "tts_path": output_path,
                        "target_duration": target_duration,
                        "initial_tts_duration": duration,
                        "tts_duration": duration,
                        "duration_status": duration_status,
                        "duration_error_seconds": duration - target_duration,
                        "correction_actions": [],
                        "time_stretch_ratio": None,
                    }
                )
            )
        return transcript.model_copy(update={"segments": synthesized_segments})
