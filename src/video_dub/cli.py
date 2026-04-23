from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich import print

from video_dub.config import load_config
from video_dub.models.manifest import RunManifest
from video_dub.models.transcript import TranscriptDocument
from video_dub.pipeline import (
    build_manual_review_segment_row,
    initialize_run,
    require_manifest_input_video,
    run_extract_and_transcribe,
    run_translate_and_subtitle,
    run_tts_compose_and_mux,
)
from video_dub.services.repair import (
    apply_segment_repairs,
    load_repair_rows,
    rebuild_run_outputs,
)
from video_dub.storage.artifacts import ArtifactStore
from video_dub.storage.json_store import read_model, write_json
from video_dub.storage.run_layout import RunLayout

load_dotenv()

app = typer.Typer(help="English to Kazakh video dubbing pipeline")

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")
DEFAULT_CONFIG_PATH_STR = str(DEFAULT_CONFIG_PATH)

InputVideoOption = Annotated[
    Path,
    typer.Option(exists=True, file_okay=True, dir_okay=False),
]
RunDirOption = Annotated[
    Path,
    typer.Option(exists=True, file_okay=False, dir_okay=True),
]
ConfigOption = Annotated[
    Path,
    typer.Option(exists=True, file_okay=True, dir_okay=False),
]
RepairFileOption = Annotated[
    Path,
    typer.Option(exists=True, file_okay=True, dir_okay=False),
]
JobIdOption = Annotated[str | None, typer.Option()]
OptionalOutputOption = Annotated[Path | None, typer.Option()]


def load_existing_context(run_dir: Path, config_path: Path):
    app_config = load_config(config_path)
    layout = RunLayout(run_dir)
    store = ArtifactStore(layout)
    manifest = read_model(layout.manifest_path, RunManifest)
    context = initialize_run(
        app_config,
        require_manifest_input_video(manifest.input_video),
        job_id=manifest.job_id,
    )
    context.manifest = manifest
    context.store = store
    return context


@app.command()
def run(
    input: InputVideoOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    job_id: JobIdOption = None,
) -> None:
    app_config = load_config(config)
    context = initialize_run(app_config, input, job_id=job_id)
    transcript = run_extract_and_transcribe(context)
    transcript_kk, _ = run_translate_and_subtitle(context, transcript)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Initialized run at {context.layout.run_dir}")
    print(f"Extracted audio to {context.layout.source_audio_path}")
    print(
        f"Produced {len(transcript.segments)} transcript segments at "
        f"{context.layout.transcript_en_path}"
    )
    print(
        f"Produced {len(transcript_kk.segments)} translated segments at "
        f"{context.layout.transcript_kk_path}"
    )
    print(f"Generated {len(transcript_with_tts.segments)} TTS segments in {context.layout.tts_dir}")
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")


@app.command()
def transcribe(
    input: InputVideoOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    job_id: JobIdOption = None,
) -> None:
    app_config = load_config(config)
    context = initialize_run(app_config, input, job_id=job_id)
    transcript = run_extract_and_transcribe(context)
    print(
        f"Produced {len(transcript.segments)} transcript segments at "
        f"{context.layout.transcript_en_path}"
    )


@app.command()
def translate(
    run_dir: RunDirOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    context = load_existing_context(run_dir, config)
    transcript = read_model(context.layout.transcript_en_path, TranscriptDocument)
    transcript_kk, _ = run_translate_and_subtitle(context, transcript)
    print(
        f"Produced {len(transcript_kk.segments)} translated segments at "
        f"{context.layout.transcript_kk_path}"
    )
    print(f"Wrote subtitles to {context.layout.subtitles_zh_path}")


@app.command()
def tts(
    run_dir: RunDirOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    context = load_existing_context(run_dir, config)
    transcript_kk = read_model(context.layout.transcript_kk_path, TranscriptDocument)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Generated {len(transcript_with_tts.segments)} TTS segments in {context.layout.tts_dir}")
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")


@app.command()
def compose(
    run_dir: RunDirOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    context = load_existing_context(run_dir, config)
    transcript_kk = read_model(context.layout.transcript_kk_path, TranscriptDocument)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")
    print(f"Used {len(transcript_with_tts.segments)} synthesized segments")


@app.command("repair-export")
def repair_export(
    run_dir: RunDirOption,
    output: OptionalOutputOption = None,
) -> None:
    layout = RunLayout(run_dir)
    transcript = read_model(layout.transcript_kk_path, TranscriptDocument)
    rows = [
        build_manual_review_segment_row(segment)
        for segment in transcript.segments
        if segment.duration_status == "manual_review"
    ]

    output_path = output or layout.manual_review_segments_path
    write_json(output_path, rows)
    print(f"Exported {len(rows)} manual review segments to {output_path}")


@app.command("repair-show")
def repair_show(
    run_dir: RunDirOption,
) -> None:
    layout = RunLayout(run_dir)
    transcript = read_model(layout.transcript_kk_path, TranscriptDocument)
    rows = [
        build_manual_review_segment_row(segment)
        for segment in transcript.segments
        if segment.duration_status == "manual_review"
    ]

    if not rows:
        print("No manual review segments found")
        return

    print(f"Found {len(rows)} manual review segments in {run_dir}")
    for row in rows:
        print(
            f"- {row['segment_id']}: reason={row['manual_review_reason']} "
            f"status={row['duration_status']} error={row['duration_error_seconds']} "
            f"overhang={row['timeline_overhang_seconds']}"
        )


@app.command("repair-apply")
def repair_apply(
    run_dir: RunDirOption,
    repair_file: RepairFileOption,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
) -> None:
    context = load_existing_context(run_dir, config)
    transcript = read_model(context.layout.transcript_kk_path, TranscriptDocument)
    repair_rows = load_repair_rows(repair_file)
    updated_transcript = apply_segment_repairs(
        run_dir=run_dir,
        transcript=transcript,
        repair_rows=repair_rows,
        config=context.config,
        store=context.store,
    )
    remaining_rows = rebuild_run_outputs(
        run_dir=run_dir,
        transcript=updated_transcript,
        manifest=context.manifest,
        config=context.config,
        store=context.store,
    )
    print(f"Applied repairs for {len(repair_rows)} requested segments in {run_dir}")
    print(f"Remaining manual review segments: {len(remaining_rows)}")


if __name__ == "__main__":
    app()
