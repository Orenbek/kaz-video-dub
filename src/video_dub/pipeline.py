from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import shutil

from video_dub.config import AppConfig
from video_dub.models.manifest import RunManifest
from video_dub.storage.artifacts import ArtifactStore
from video_dub.storage.run_layout import RunLayout


@dataclass
class PipelineContext:
    config: AppConfig
    layout: RunLayout
    store: ArtifactStore
    manifest: RunManifest


def make_job_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def initialize_run(config: AppConfig, input_video: Path, job_id: str | None = None) -> PipelineContext:
    resolved_job_id = job_id or make_job_id()
    layout = RunLayout(config.run_root / resolved_job_id)
    layout.ensure()

    copied_input = layout.input_dir / input_video.name
    if input_video.resolve() != copied_input.resolve():
        shutil.copy2(input_video, copied_input)

    manifest = RunManifest(
        job_id=resolved_job_id,
        input_video=copied_input,
        source_language=config.source_language,
        target_language=config.target_language,
        subtitle_language=config.subtitle_language,
    )
    store = ArtifactStore(layout)
    store.write_manifest(manifest)
    return PipelineContext(config=config, layout=layout, store=store, manifest=manifest)
