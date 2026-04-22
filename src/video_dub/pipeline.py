from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import shutil

from video_dub.config import AppConfig
from video_dub.models.manifest import DurationSummary, RunManifest
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_translate_provider import GeminiTranslateConfig, GeminiTranslateProvider
from video_dub.providers.gemini_tts_provider import GeminiTTSConfig, GeminiTTSProvider
from video_dub.providers.whisperx_provider import WhisperXConfig, WhisperXProvider
from video_dub.services.audio_compose import AudioComposeService
from video_dub.services.audio_extract import AudioExtractor
from video_dub.services.subtitle import write_srt
from video_dub.services.synthesis import SynthesisService, summarize_duration_statuses
from video_dub.services.transcription import TranscriptionService
from video_dub.services.translation import TranslationService
from video_dub.services.video_mux import VideoMuxService
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
        input_video=str(copied_input),
        source_language=config.source_language,
        target_language=config.target_language,
        subtitle_language=config.subtitle_language,
    )
    store = ArtifactStore(layout)
    store.write_manifest(manifest)
    return PipelineContext(config=config, layout=layout, store=store, manifest=manifest)


def build_translation_service(config: AppConfig) -> TranslationService:
    provider = GeminiTranslateProvider(
        GeminiTranslateConfig(
            model_name=config.translation.model_name,
            use_stub=config.translation.use_stub,
            max_retries=config.translation.max_retries,
            retry_delay_seconds=config.translation.retry_delay_seconds,
        )
    )
    return TranslationService(provider)


def build_tts_service(config: AppConfig) -> SynthesisService:
    provider = GeminiTTSProvider(
        GeminiTTSConfig(
            model_name=config.tts.model_name,
            use_stub=config.tts.use_stub,
            sample_rate=config.tts.sample_rate,
            max_retries=config.tts.max_retries,
            retry_delay_seconds=config.tts.retry_delay_seconds,
        )
    )
    return SynthesisService(provider, config.tts_alignment)


def run_extract_and_transcribe(context: PipelineContext) -> TranscriptDocument:
    extractor = AudioExtractor(context.config)
    extractor.extract(Path(context.manifest.input_video), context.layout.source_audio_path)
    context.manifest.steps["extract_audio"] = "done"
    context.manifest.artifacts["source_audio"] = str(context.layout.source_audio_path)
    context.store.write_manifest(context.manifest)

    provider = WhisperXProvider(
        WhisperXConfig(
            language=context.config.source_language,
        )
    )
    service = TranscriptionService(provider)
    transcript = service.run(context.layout.source_audio_path)
    context.store.write_transcript_en(transcript)
    context.manifest.steps["transcribe"] = "done"
    context.manifest.steps["align"] = "done"
    context.manifest.artifacts["transcript_en"] = str(context.layout.transcript_en_path)
    context.store.write_manifest(context.manifest)
    return transcript


def run_translate_and_subtitle(
    context: PipelineContext,
    transcript: TranscriptDocument,
) -> tuple[TranscriptDocument, TranscriptDocument]:
    service = build_translation_service(context.config)

    transcript_kk = service.to_kazakh(transcript)
    context.store.write_transcript_kk(transcript_kk)
    context.manifest.steps["translate"] = "done"
    context.manifest.artifacts["transcript_kk"] = str(context.layout.transcript_kk_path)
    context.store.write_manifest(context.manifest)

    transcript_zh = service.to_chinese_subtitles(transcript)
    write_srt(context.layout.subtitles_zh_path, transcript_zh)
    context.manifest.steps["subtitle"] = "done"
    context.manifest.artifacts["subtitles_zh"] = str(context.layout.subtitles_zh_path)
    context.store.write_manifest(context.manifest)
    return transcript_kk, transcript_zh


def run_tts_compose_and_mux(context: PipelineContext, transcript_kk: TranscriptDocument) -> TranscriptDocument:
    tts_service = build_tts_service(context.config)
    transcript_with_tts = tts_service.run(
        transcript_kk,
        tts_dir=context.layout.tts_dir,
        voice=context.config.tts.voice,
    )
    duration_summary = summarize_duration_statuses(transcript_with_tts)
    context.manifest.duration_summary = DurationSummary(**duration_summary)

    compose_service = AudioComposeService(context.config.tts_alignment)
    prepared_transcript = compose_service.prepare_transcript(transcript_with_tts)
    context.store.write_transcript_kk_with_tts(prepared_transcript)
    context.manifest.steps["tts"] = "done"
    context.manifest.artifacts["tts_dir"] = str(context.layout.tts_dir)
    context.store.write_manifest(context.manifest)
    print(
        "TTS summary: "
        f"total={duration_summary['total_segments']} "
        f"preferred={duration_summary['preferred_count']} "
        f"acceptable={duration_summary['acceptable_count']} "
        f"flagged={duration_summary['flagged_count']} "
        f"manual_review={duration_summary['manual_review_count']}"
    )

    compose_service.compose(prepared_transcript, context.layout.dub_audio_path)
    context.manifest.steps["compose_audio"] = "done"
    context.manifest.artifacts["dub_audio"] = str(context.layout.dub_audio_path)
    context.store.write_manifest(context.manifest)

    mux_service = VideoMuxService()
    mux_service.mux_soft_subtitle(
        input_video=Path(context.manifest.input_video),
        dub_audio=context.layout.dub_audio_path,
        subtitle_srt=context.layout.subtitles_zh_path,
        output_video=context.layout.final_video_path,
    )
    context.manifest.steps["mux_video"] = "done"
    context.manifest.artifacts["final_video"] = str(context.layout.final_video_path)
    context.store.write_manifest(context.manifest)
    return prepared_transcript
