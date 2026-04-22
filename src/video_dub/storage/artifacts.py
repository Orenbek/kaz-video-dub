from __future__ import annotations

from pathlib import Path

from video_dub.models.manifest import RunManifest
from video_dub.models.transcript import TranscriptDocument
from video_dub.storage.json_store import write_model
from video_dub.storage.run_layout import RunLayout


class ArtifactStore:
    def __init__(self, layout: RunLayout) -> None:
        self.layout = layout

    def write_manifest(self, manifest: RunManifest) -> None:
        write_model(self.layout.manifest_path, manifest)

    def write_transcript_en(self, transcript: TranscriptDocument) -> None:
        write_model(self.layout.transcript_en_path, transcript)

    def write_transcript_en_diarized(self, transcript: TranscriptDocument) -> None:
        write_model(self.layout.transcript_en_diarized_path, transcript)

    def write_transcript_kk(self, transcript: TranscriptDocument) -> None:
        write_model(self.layout.transcript_kk_path, transcript)

    def write_transcript_kk_with_tts(self, transcript: TranscriptDocument) -> None:
        write_model(self.layout.transcript_kk_path, transcript)

    def tts_path_for_segment(self, segment_id: str, suffix: str = ".wav") -> Path:
        return self.layout.tts_dir / f"{segment_id}{suffix}"
