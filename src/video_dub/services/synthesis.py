from __future__ import annotations

from pathlib import Path

from video_dub.ffmpeg.probe import probe_duration
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_tts_provider import GeminiTTSProvider


class SynthesisService:
    def __init__(self, provider: GeminiTTSProvider) -> None:
        self.provider = provider

    def run(self, transcript: TranscriptDocument, tts_dir: Path, voice: str) -> TranscriptDocument:
        synthesized_segments = []
        for segment in transcript.segments:
            output_path = tts_dir / f"{segment.id}.wav"
            self.provider.synthesize_segment(segment, output_path, voice)
            duration = probe_duration(output_path)
            synthesized_segments.append(
                segment.model_copy(
                    update={
                        "tts_path": output_path,
                        "tts_duration": duration,
                    }
                )
            )
        return transcript.model_copy(update={"segments": synthesized_segments})
