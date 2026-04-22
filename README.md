# kaz-video-dub

A minimal English → Kazakh video dubbing pipeline focused on a stable first runnable version.

## Goals
- Extract audio from video
- Transcribe and align English segments
- Optionally diarize speakers
- Translate English to Kazakh
- Generate Chinese subtitles
- Synthesize Kazakh dubbing audio
- Compose final dubbed audio and mux output video

## Environment
This project uses Pixi on macOS Apple Silicon (`osx-arm64`).

## Quick start
```bash
pixi install
pixi run run --input path/to/input.mp4
```

## Common commands
```bash
pixi run test
pixi run lint
pixi run fmt
```

## Notes
- The first version keeps all intermediate artifacts on disk under `runs/`.
- The pipeline is organized around a unified segment data model.
