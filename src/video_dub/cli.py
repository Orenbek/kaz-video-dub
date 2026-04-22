from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich import print

from video_dub.config import load_config
from video_dub.models.manifest import RunManifest
from video_dub.models.transcript import TranscriptDocument
from video_dub.pipeline import (
    initialize_run,
    run_extract_and_transcribe,
    run_translate_and_subtitle,
    run_tts_compose_and_mux,
)
from video_dub.storage.artifacts import ArtifactStore
from video_dub.storage.json_store import read_model
from video_dub.storage.run_layout import RunLayout

load_dotenv()

app = typer.Typer(help="English to Kazakh video dubbing pipeline")


def load_existing_context(run_dir: Path, config_path: Path):
    app_config = load_config(config_path)
    layout = RunLayout(run_dir)
    store = ArtifactStore(layout)
    manifest = read_model(layout.manifest_path, RunManifest)
    context = initialize_run(app_config, manifest.input_video, job_id=manifest.job_id)
    context.manifest = manifest
    context.store = store
    return context


@app.command()
def run(
    input: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
    job_id: str | None = typer.Option(None),
) -> None:
    app_config = load_config(config)
    context = initialize_run(app_config, input, job_id=job_id)
    transcript = run_extract_and_transcribe(context)
    transcript_kk, _ = run_translate_and_subtitle(context, transcript)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Initialized run at {context.layout.run_dir}")
    print(f"Extracted audio to {context.layout.source_audio_path}")
    print(f"Produced {len(transcript.segments)} transcript segments at {context.layout.transcript_en_path}")
    print(f"Produced {len(transcript_kk.segments)} translated segments at {context.layout.transcript_kk_path}")
    print(f"Generated {len(transcript_with_tts.segments)} TTS segments in {context.layout.tts_dir}")
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")


@app.command()
def transcribe(
    input: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
    job_id: str | None = typer.Option(None),
) -> None:
    app_config = load_config(config)
    context = initialize_run(app_config, input, job_id=job_id)
    transcript = run_extract_and_transcribe(context)
    print(f"Produced {len(transcript.segments)} transcript segments at {context.layout.transcript_en_path}")


@app.command()
def translate(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
) -> None:
    context = load_existing_context(run_dir, config)
    transcript = read_model(context.layout.transcript_en_path, TranscriptDocument)
    transcript_kk, _ = run_translate_and_subtitle(context, transcript)
    print(f"Produced {len(transcript_kk.segments)} translated segments at {context.layout.transcript_kk_path}")
    print(f"Wrote subtitles to {context.layout.subtitles_zh_path}")


@app.command()
def tts(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
) -> None:
    context = load_existing_context(run_dir, config)
    transcript_kk = read_model(context.layout.transcript_kk_path, TranscriptDocument)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Generated {len(transcript_with_tts.segments)} TTS segments in {context.layout.tts_dir}")
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")


@app.command()
def compose(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False, dir_okay=True),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
) -> None:
    context = load_existing_context(run_dir, config)
    transcript_kk = read_model(context.layout.transcript_kk_path, TranscriptDocument)
    transcript_with_tts = run_tts_compose_and_mux(context, transcript_kk)
    print(f"Composed dubbed audio at {context.layout.dub_audio_path}")
    print(f"Muxed final video at {context.layout.final_video_path}")
    print(f"Used {len(transcript_with_tts.segments)} synthesized segments")


if __name__ == "__main__":
    app()
