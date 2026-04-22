from __future__ import annotations

from pathlib import Path

import typer
from rich import print

from video_dub.config import load_config
from video_dub.pipeline import initialize_run
from video_dub.services.audio_extract import AudioExtractor

app = typer.Typer(help="English to Kazakh video dubbing pipeline")


@app.command()
def run(
    input: Path = typer.Option(..., exists=True, file_okay=True, dir_okay=False),
    config: Path = typer.Option(Path("configs/default.yaml"), exists=True, file_okay=True, dir_okay=False),
    job_id: str | None = typer.Option(None),
) -> None:
    app_config = load_config(config)
    context = initialize_run(app_config, input, job_id=job_id)
    extractor = AudioExtractor(app_config)
    command = extractor.build_command(context.manifest.input_video, context.layout.source_audio_path)
    print(f"Initialized run at {context.layout.run_dir}")
    print(f"Extract audio command: {command}")


@app.command()
def transcribe() -> None:
    print("Transcribe entrypoint is scaffolded but not implemented yet.")


@app.command()
def translate() -> None:
    print("Translate entrypoint is scaffolded but not implemented yet.")


@app.command()
def tts() -> None:
    print("TTS entrypoint is scaffolded but not implemented yet.")


@app.command()
def compose() -> None:
    print("Compose entrypoint is scaffolded but not implemented yet.")


if __name__ == "__main__":
    app()
