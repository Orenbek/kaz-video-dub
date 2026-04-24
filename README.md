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

## Setup
```bash
cp .env.example .env
pixi install
```

The CLI now auto-loads `.env` via `python-dotenv`.

Set these before real provider runs:
- `GEMINI_API_KEY` for Gemini translation and TTS
- `HF_TOKEN` for WhisperX alignment / pyannote gated assets when needed

## Quick start
Stub mode is enabled by default for Gemini translation and TTS, so the pipeline structure can run before full API wiring.

```bash
pixi run run --input path/to/input.mp4
```

If the source video is silent and the audio was downloaded separately, pass the video as
`--input` and the audio as `--input-audio`:

```bash
pixi run run --input path/to/video.mp4 --input-audio path/to/audio.m4a
```

The run manifest records both files. Transcription uses `--input-audio` when present, while
the final mux still uses the video from `--input`.

## Real provider run
1. Edit `configs/default.yaml`
2. Set:
   - `translation.use_stub: false`
   - `tts.use_stub: false`
3. Make sure `.env` contains `GEMINI_API_KEY`
4. If WhisperX or pyannote gated models require it, set `HF_TOKEN`
5. Tune retries if preview APIs are flaky:
   - `translation.max_retries`
   - `translation.retry_delay_seconds`
   - `tts.max_retries`
   - `tts.retry_delay_seconds`
6. Run:

```bash
pixi run run --input path/to/input.mp4
```

## Real Gemini TTS notes
The project is wired for the Gemini API Python SDK pattern documented for TTS:
- model: `gemini-3.1-flash-tts-preview`
- response modality: `AUDIO`
- voice field: `speech_config.voice_config.prebuilt_voice_config.voice_name`
- audio bytes path: `response.candidates[0].content.parts[0].inline_data.data`
- saved as mono 24kHz 16-bit PCM WAV

Default config is in `configs/default.yaml:1`.
Default voice is `Kore`, based on the Google TTS example shape. You can change it in `configs/default.yaml:1`.

## Documentation
- `docs/designs/` — near-term technical designs intended to guide implementation.
- `docs/plans/` — implementation plans with phased engineering tasks and target files.
- `docs/proposals/` — future-facing proposals that define direction without committing immediate engineering work.

## Common commands
```bash
pixi run run --input path/to/input.mp4
pixi run run --input path/to/video.mp4 --input-audio path/to/audio.m4a
pixi run transcribe --input path/to/input.mp4
pixi run transcribe --input path/to/video.mp4 --input-audio path/to/audio.m4a
pixi run translate --run-dir runs/<job-id>
pixi run tts --run-dir runs/<job-id>
pixi run compose --run-dir runs/<job-id>
pixi run repair-show --run-dir runs/<job-id>
pixi run repair-export --run-dir runs/<job-id>
pixi run test
pixi run lint
pixi run fmt
pixi run typecheck
```

## Notes
- The first version keeps all intermediate artifacts on disk under `runs/`.
- The pipeline is organized around a unified segment data model.
- Current Gemini TTS integration is single-speaker only.
- Real Gemini TTS is preview-mode API surface, so response quirks and retries may still need hardening.
- Run `pixi run test` after `pixi install`; the system Python in this repo is not the intended runtime.
