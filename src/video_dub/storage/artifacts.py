from __future__ import annotations

from pathlib import Path

from video_dub.models.manifest import RunManifest
from video_dub.storage.json_store import write_model
from video_dub.storage.run_layout import RunLayout


class ArtifactStore:
    def __init__(self, layout: RunLayout) -> None:
        self.layout = layout

    def write_manifest(self, manifest: RunManifest) -> None:
        write_model(self.layout.manifest_path, manifest)

    def tts_path_for_segment(self, segment_id: str, suffix: str = ".wav") -> Path:
        return self.layout.tts_dir / f"{segment_id}{suffix}"
