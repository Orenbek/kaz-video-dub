from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_dub.config import AppConfig
from video_dub.models.manifest import DurationSummary, RunManifest
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.pipeline import (
    build_manual_review_segment_row,
    build_tts_service,
    require_manifest_input_video,
)
from video_dub.services.audio_compose import AudioComposeService
from video_dub.services.synthesis import resolve_segment_voice, summarize_duration_statuses
from video_dub.services.video_mux import VideoMuxService
from video_dub.storage.artifacts import ArtifactStore
from video_dub.storage.json_store import write_json
from video_dub.storage.run_layout import RunLayout


def load_repair_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Repair file must contain a JSON array: {path}")
    return payload


def apply_segment_repairs(
    *,
    run_dir: Path,
    transcript: TranscriptDocument,
    repair_rows: list[dict[str, Any]],
    config: AppConfig,
    store: ArtifactStore,
) -> TranscriptDocument:
    layout = RunLayout(run_dir)
    tts_service = build_tts_service(config)
    compose_service = AudioComposeService(config.tts_alignment)
    rows_by_id = {row["segment_id"]: row for row in repair_rows if row.get("segment_id")}

    updated_segments: list[Segment] = []
    for index, segment in enumerate(transcript.segments):
        repair_row = rows_by_id.get(segment.id)
        if repair_row is None:
            updated_segments.append(segment)
            continue

        repaired_text = repair_row.get("text_kk")
        if not isinstance(repaired_text, str) or not repaired_text.strip():
            raise RuntimeError(
                f"Repair row for segment {segment.id} must provide non-empty text_kk"
            )

        repaired_segment = segment.model_copy(
            update={
                "text_kk": repaired_text.strip(),
                "duration_status": None,
                "duration_error_seconds": None,
                "correction_actions": [],
                "time_stretch_ratio": None,
                "has_timeline_collision": None,
            }
        )
        next_segment = (
            transcript.segments[index + 1] if index + 1 < len(transcript.segments) else None
        )
        synthesized = tts_service.process_segment(
            segment=repaired_segment,
            next_segment=next_segment,
            tts_dir=layout.tts_dir,
            raw_tts_dir=layout.tts_raw_dir,
            voice=resolve_segment_voice(
                repaired_segment,
                config.tts.gemini_voice_names.get("SPEAKER_00", config.tts.voice),
                config.tts.gemini_voice_names,
            ),
        )
        prepared = compose_service.prepare_segment(synthesized, next_segment)
        updated_segments.append(prepared)

    updated_transcript = transcript.model_copy(update={"segments": updated_segments})
    store.write_transcript_kk_with_tts(updated_transcript)
    return updated_transcript


def rebuild_run_outputs(
    *,
    run_dir: Path,
    transcript: TranscriptDocument,
    manifest: RunManifest,
    config: AppConfig,
    store: ArtifactStore,
) -> list[dict[str, Any]]:
    layout = RunLayout(run_dir)
    compose_service = AudioComposeService(config.tts_alignment)
    compose_service.compose(transcript, layout.dub_audio_path)

    mux_service = VideoMuxService()
    input_video = require_manifest_input_video(manifest.input_video)
    if config.video.subtitle_mode == "hard":
        mux_service.mux_hard_subtitle(
            input_video=input_video,
            dub_audio=layout.dub_audio_path,
            subtitle_srt=layout.subtitles_zh_path,
            output_video=layout.final_video_path,
        )
    else:
        mux_service.mux_soft_subtitle(
            input_video=input_video,
            dub_audio=layout.dub_audio_path,
            subtitle_srt=layout.subtitles_zh_path,
            output_video=layout.final_video_path,
        )

    duration_summary = summarize_duration_statuses(transcript)
    manifest.duration_summary = DurationSummary.model_validate(duration_summary)
    manifest.artifacts["dub_audio"] = str(layout.dub_audio_path)
    manifest.artifacts["final_video"] = str(layout.final_video_path)
    manifest.artifacts["subtitle_mode"] = config.video.subtitle_mode

    manual_review_rows = [
        build_manual_review_segment_row(segment)
        for segment in transcript.segments
        if segment.duration_status == "manual_review"
    ]
    write_json(layout.manual_review_segments_path, manual_review_rows)
    manifest.artifacts["manual_review_segments"] = str(layout.manual_review_segments_path)
    store.write_manifest(manifest)
    return manual_review_rows
