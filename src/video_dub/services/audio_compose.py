from __future__ import annotations

import subprocess
from pathlib import Path

from video_dub.config import TTSAlignmentConfig
from video_dub.ffmpeg.commands import compose_dub_audio_command
from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


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
            max_safe_duration = max(0.0, allowed_end - segment.start)
            if actual_duration > max_safe_duration:
                trimmed_duration = self._trim_trailing_silence(segment.tts_path, max_safe_duration)
                if trimmed_duration < actual_duration:
                    actual_duration = trimmed_duration
                    if "trim_trailing_silence" not in correction_actions:
                        correction_actions.append("trim_trailing_silence")
                if actual_duration > max_safe_duration:
                    status = "manual_review" if self.alignment.manual_review_on_failure else (segment.duration_status or "too_long")
                    return segment.model_copy(
                        update={
                            "tts_duration": actual_duration,
                            "duration_status": status,
                            "duration_error_seconds": actual_duration - target_duration,
                            "correction_actions": correction_actions,
                        }
                    )

        return segment.model_copy(
            update={
                "tts_duration": actual_duration,
                "duration_error_seconds": actual_duration - target_duration,
                "correction_actions": correction_actions,
            }
        )

    def _trim_trailing_silence(self, path: Path, max_duration: float) -> float:
        current_duration = probe_duration(path)
        return min(current_duration, max_duration)
