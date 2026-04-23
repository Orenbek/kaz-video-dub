from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from video_dub.config import TTSAlignmentConfig
from video_dub.ffmpeg.commands import compose_dub_audio_command
from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.synthesis import (
    MANUAL_REVIEW_PLACEHOLDER,
    classify_duration_only,
    compute_duration_error,
    compute_max_safe_duration,
)


@dataclass
class TrimResult:
    applied: bool
    output_path: Path
    duration: float


class AudioComposeService:
    def __init__(self, alignment: TTSAlignmentConfig) -> None:
        self.alignment = alignment

    def build_ffmpeg_command(self, transcript: TranscriptDocument, output_path: Path) -> str:
        return compose_dub_audio_command(transcript, output_path)

    def compose(self, transcript: TranscriptDocument, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_ffmpeg_command(transcript, output_path)
        subprocess.run(command, shell=True, check=True)
        return output_path

    def prepare_transcript(self, transcript: TranscriptDocument) -> TranscriptDocument:
        if not self.alignment.enabled:
            return transcript

        prepared_segments = []
        for index, segment in enumerate(transcript.segments):
            next_segment = transcript.segments[index + 1] if index + 1 < len(transcript.segments) else None
            prepared_segments.append(self.prepare_segment(segment, next_segment))
        return transcript.model_copy(update={"segments": prepared_segments})

    def prepare_segment(self, segment: Segment, next_segment: Segment | None) -> Segment:
        if not segment.tts_path or segment.tts_duration is None:
            return segment

        correction_actions = list(segment.correction_actions)
        actual_duration = segment.tts_duration
        target_duration = segment.target_duration or segment.duration
        allowed_end = None if next_segment is None else next_segment.start + self.alignment.allow_minor_overhang_seconds

        if actual_duration < target_duration and self.alignment.pad_with_silence and "pad_silence" not in correction_actions:
            correction_actions.append("pad_silence")

        if allowed_end is not None:
            max_safe_duration = compute_max_safe_duration(segment, next_segment, self.alignment)
            assert max_safe_duration is not None
            if actual_duration > max_safe_duration:
                trimmed_duration = actual_duration
                trimmed_path = segment.tts_path
                if self.alignment.trim_trailing_silence:
                    trim_result = self._trim_trailing_silence(segment.tts_path, max_safe_duration)
                    trimmed_duration = trim_result.duration
                    trimmed_path = trim_result.output_path
                if trimmed_duration < actual_duration:
                    actual_duration = trimmed_duration
                    if "trim_trailing_silence" not in correction_actions:
                        correction_actions.append("trim_trailing_silence")
                    segment = segment.model_copy(update={"tts_path": trimmed_path})
                if actual_duration > max_safe_duration:
                    unresolved_status = "manual_review" if self.alignment.manual_review_on_failure else (segment.duration_status or "too_long")
                    return segment.model_copy(
                        update={
                            "tts_duration": actual_duration,
                            "duration_status": unresolved_status,
                            "duration_error_seconds": compute_duration_error(target_duration, actual_duration),
                            "correction_actions": correction_actions,
                            "has_timeline_collision": True,
                        }
                    )

        status: str | None = cast(str | None, segment.duration_status)
        if status == MANUAL_REVIEW_PLACEHOLDER:
            status = classify_duration_only(
                target_duration=target_duration,
                actual_duration=actual_duration,
                alignment=self.alignment,
            )
        elif status is None:
            status = classify_duration_only(
                target_duration=target_duration,
                actual_duration=actual_duration,
                alignment=self.alignment,
            )

        return segment.model_copy(
            update={
                "tts_duration": actual_duration,
                "duration_status": status,
                "duration_error_seconds": compute_duration_error(target_duration, actual_duration),
                "correction_actions": correction_actions,
                "has_timeline_collision": False,
            }
        )

    def _trim_trailing_silence(self, path: Path, max_duration: float) -> TrimResult:
        current_duration = probe_duration(path)
        if current_duration <= max_duration:
            return TrimResult(applied=False, output_path=path, duration=current_duration)

        if not path.exists() or path.suffix.lower() != ".wav":
            return TrimResult(applied=False, output_path=path, duration=current_duration)

        max_trim_seconds = max(0.0, self.alignment.max_trailing_silence_trim_seconds)
        desired_trim_seconds = min(current_duration - max_duration, max_trim_seconds)
        if desired_trim_seconds <= 0:
            return TrimResult(applied=False, output_path=path, duration=current_duration)

        silence_duration = self._detect_trailing_silence(path)
        trim_seconds = min(silence_duration, desired_trim_seconds)
        if trim_seconds <= 0:
            return TrimResult(applied=False, output_path=path, duration=current_duration)

        output_path = path.with_name(f"{path.stem}.trimmed{path.suffix}")
        trimmed_duration = self._write_trimmed_wav(path, output_path, trim_seconds)
        return TrimResult(applied=True, output_path=output_path, duration=trimmed_duration)

    def _detect_trailing_silence(self, path: Path, silence_threshold: int = 200, chunk_ms: int = 20) -> float:
        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            frame_count = wav_file.getnframes()
            chunk_frames = max(1, int(sample_rate * chunk_ms / 1000))
            total_silent_frames = 0

            while frame_count > 0:
                read_frames = min(chunk_frames, frame_count)
                frame_count -= read_frames
                wav_file.setpos(frame_count)
                chunk = wav_file.readframes(read_frames)
                if not chunk:
                    break
                rms = self._compute_rms(chunk, sample_width)
                if rms > silence_threshold:
                    break
                total_silent_frames += read_frames

        return total_silent_frames / sample_rate if sample_rate else 0.0

    def _compute_rms(self, chunk: bytes, sample_width: int) -> float:
        if sample_width != 2 or not chunk:
            return 0.0
        sample_count = len(chunk) // sample_width
        if sample_count == 0:
            return 0.0

        total = 0.0
        for offset in range(0, len(chunk), sample_width):
            sample = int.from_bytes(chunk[offset : offset + sample_width], byteorder="little", signed=True)
            total += sample * sample
        return (total / sample_count) ** 0.5

    def _write_trimmed_wav(self, input_path: Path, output_path: Path, trim_seconds: float) -> float:
        with wave.open(str(input_path), "rb") as reader:
            params = reader.getparams()
            frame_rate = reader.getframerate()
            total_frames = reader.getnframes()
            trim_frames = min(total_frames, int(trim_seconds * frame_rate))
            keep_frames = max(0, total_frames - trim_frames)
            audio_data = reader.readframes(keep_frames)

        with wave.open(str(output_path), "wb") as writer:
            writer.setparams(params)
            writer.writeframes(audio_data)

        return keep_frames / frame_rate if frame_rate else 0.0
