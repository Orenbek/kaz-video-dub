from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from video_dub.config import AppConfig
from video_dub.models.manifest import DurationSummary, RunManifest
from video_dub.models.transcript import TranscriptDocument
from video_dub.providers.gemini_translate_provider import (
    GeminiTranslateConfig,
    GeminiTranslateProvider,
)
from video_dub.providers.gemini_tts import (
    DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE,
    GeminiTTSConfig,
    GeminiTTSProvider,
)
from video_dub.providers.pyannote_provider import PyannoteConfig, PyannoteProvider
from video_dub.providers.whisperx_provider import WhisperXConfig, WhisperXProvider
from video_dub.services.audio_compose import AudioComposeService
from video_dub.services.audio_extract import AudioExtractor
from video_dub.services.diarization import DiarizationService
from video_dub.services.subtitle import write_srt
from video_dub.services.synthesis import (
    SynthesisService,
    compute_max_safe_duration,
    summarize_duration_statuses,
)
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


def build_manual_review_segment_row(segment: Any) -> dict[str, Any]:
    timeline_overhang_seconds = None
    next_segment = getattr(segment, "next_segment_for_manual_review", None)
    alignment = getattr(segment, "alignment_for_manual_review", None)
    if (
        segment.has_timeline_collision
        and segment.tts_duration is not None
        and alignment is not None
    ):
        max_safe_duration = compute_max_safe_duration(
            segment,
            next_segment,
            alignment,
        )
        if max_safe_duration is not None:
            timeline_overhang_seconds = round(max(0.0, segment.tts_duration - max_safe_duration), 6)

    if segment.has_timeline_collision:
        manual_review_reason = "timeline_collision_unresolved"
    elif segment.duration_status == "manual_review":
        manual_review_reason = "duration_manual_review"
    else:
        manual_review_reason = None

    return {
        "segment_id": segment.id,
        "start": segment.start,
        "end": segment.end,
        "text_en": segment.text_en,
        "text_kk": segment.text_kk,
        "target_duration": segment.target_duration,
        "initial_tts_duration": segment.initial_tts_duration,
        "tts_duration": segment.tts_duration,
        "duration_error_seconds": segment.duration_error_seconds,
        "has_timeline_collision": segment.has_timeline_collision,
        "timeline_overhang_seconds": timeline_overhang_seconds,
        "duration_status": segment.duration_status,
        "manual_review_reason": manual_review_reason,
        "correction_actions": segment.correction_actions,
        "time_stretch_ratio": segment.time_stretch_ratio,
        "raw_tts_path": str(segment.raw_tts_path) if segment.raw_tts_path else None,
        "tts_path": str(segment.tts_path) if segment.tts_path else None,
    }


def make_job_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def require_manifest_input_video(input_video: Path | str | None) -> Path:
    if input_video is None:
        raise RuntimeError("Run manifest is missing input_video")
    return Path(cast(Path | str, input_video))


def select_transcription_audio_source(manifest: RunManifest) -> Path:
    if manifest.input_audio is not None:
        return Path(cast(Path | str, manifest.input_audio))
    return require_manifest_input_video(manifest.input_video)


def copy_input_file(
    input_path: Path,
    input_dir: Path,
    destination_name: str | None = None,
) -> Path:
    copied_input = input_dir / (destination_name or input_path.name)
    if input_path.resolve() != copied_input.resolve():
        shutil.copy2(input_path, copied_input)
    return copied_input


def initialize_run(
    config: AppConfig,
    input_video: Path,
    job_id: str | None = None,
    input_audio: Path | None = None,
) -> PipelineContext:
    resolved_job_id = job_id or make_job_id()
    layout = RunLayout(config.run_root / resolved_job_id)
    layout.ensure()

    copied_video = copy_input_file(input_video, layout.input_dir)
    copied_audio = None
    if input_audio is not None:
        audio_name = input_audio.name
        if input_audio.resolve() != input_video.resolve() and audio_name == copied_video.name:
            audio_name = f"audio_{audio_name}"
        copied_audio = copy_input_file(input_audio, layout.input_dir, audio_name)

    manifest = RunManifest(
        job_id=resolved_job_id,
        input_video=str(copied_video),
        input_audio=str(copied_audio) if copied_audio is not None else None,
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
            request_timeout_seconds=config.translation.request_timeout_seconds,
        )
    )
    return TranslationService(provider)


def build_tts_service(config: AppConfig) -> SynthesisService:
    provider = GeminiTTSProvider(
        GeminiTTSConfig(
            model_name=config.tts.model_name,
            prompt_preamble=config.tts.gemini_prompt_preamble or DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE,
            language=config.target_language,
            use_stub=config.tts.use_stub,
            sample_rate=config.tts.sample_rate,
            max_retries=config.tts.max_retries,
            retry_delay_seconds=config.tts.retry_delay_seconds,
            request_timeout_seconds=config.tts.request_timeout_seconds,
        )
    )
    return SynthesisService(provider, config.tts_alignment)


def should_run_diarization(config: AppConfig) -> bool:
    return not (config.diarization.num_speakers == 1 and config.diarization.max_speakers == 1)


def build_diarization_service(config: AppConfig) -> DiarizationService:
    provider = PyannoteProvider(
        PyannoteConfig(
            model_name=config.diarization.model_name,
            device=config.diarization.device,
            num_speakers=config.diarization.num_speakers,
            min_speakers=config.diarization.min_speakers,
            max_speakers=config.diarization.max_speakers,
        )
    )
    return DiarizationService(provider)


def run_diarization(
    context: PipelineContext,
    transcript: TranscriptDocument,
) -> TranscriptDocument:
    if not should_run_diarization(context.config):
        print(
            "[pipeline] Skipping speaker diarization because "
            "diarization.num_speakers=1 and diarization.max_speakers=1"
        )
        single_speaker_transcript = transcript.model_copy(
            update={
                "segments": [
                    segment.model_copy(update={"speaker": segment.speaker or "SPEAKER_00"})
                    for segment in transcript.segments
                ],
                "metadata": {
                    **transcript.metadata,
                    "diarization": {
                        "provider": "single_speaker_hint",
                        "span_count": 0,
                        "speaker_count": 1 if transcript.segments else 0,
                        "assigned_segment_count": len(transcript.segments),
                    },
                },
            }
        )
        context.store.write_transcript_en_diarized(single_speaker_transcript)
        context.manifest.steps["diarize"] = "skipped"
        context.manifest.artifacts["transcript_en_diarized"] = str(
            context.layout.transcript_en_diarized_path
        )
        context.store.write_manifest(context.manifest)
        return single_speaker_transcript

    service = build_diarization_service(context.config)
    print(
        f"[pipeline] Starting speaker diarization: "
        f"model={context.config.diarization.model_name} "
        f"segments={len(transcript.segments)}"
    )
    diarized_transcript = service.run(transcript, context.layout.source_audio_path)
    summary = diarized_transcript.metadata.get("diarization", {})
    print(
        "[pipeline] Diarization finished: "
        f"speakers={summary.get('speaker_count', 0)} "
        f"spans={summary.get('span_count', 0)} "
        f"assigned_segments={summary.get('assigned_segment_count', 0)}"
    )
    context.store.write_transcript_en_diarized(diarized_transcript)
    context.manifest.steps["diarize"] = "done"
    context.manifest.artifacts["transcript_en_diarized"] = str(
        context.layout.transcript_en_diarized_path
    )
    context.store.write_manifest(context.manifest)
    return diarized_transcript


def run_extract_and_transcribe(context: PipelineContext) -> TranscriptDocument:
    extractor = AudioExtractor(context.config)
    audio_source = select_transcription_audio_source(context.manifest)
    print(f"[pipeline] Extracting transcription audio from {audio_source}")
    extractor.extract(
        audio_source,
        context.layout.source_audio_path,
    )
    print(f"[pipeline] Wrote normalized source audio to {context.layout.source_audio_path}")
    context.manifest.steps["extract_audio"] = "done"
    context.manifest.artifacts["source_audio"] = str(context.layout.source_audio_path)
    context.store.write_manifest(context.manifest)

    print("[pipeline] Starting transcription and alignment")
    provider = WhisperXProvider(
        WhisperXConfig(
            language=context.config.source_language,
        )
    )
    service = TranscriptionService(provider)
    transcript = service.run(context.layout.source_audio_path)
    print(f"[pipeline] Transcription finished: segments={len(transcript.segments)}")
    context.store.write_transcript_en(transcript)
    context.manifest.steps["transcribe"] = "done"
    context.manifest.steps["align"] = "done"
    context.manifest.artifacts["transcript_en"] = str(context.layout.transcript_en_path)
    context.store.write_manifest(context.manifest)

    return run_diarization(context, transcript)


def run_translate_and_subtitle(
    context: PipelineContext,
    transcript: TranscriptDocument,
) -> tuple[TranscriptDocument, TranscriptDocument]:
    service = build_translation_service(context.config)

    print(
        f"[pipeline] Translating transcript to {context.config.target_language}: "
        f"segments={len(transcript.segments)}"
    )
    transcript_kk = service.to_kazakh(transcript)
    context.store.write_transcript_kk(transcript_kk)
    print(f"[pipeline] Wrote target transcript to {context.layout.transcript_kk_path}")
    context.manifest.steps["translate"] = "done"
    context.manifest.artifacts["transcript_kk"] = str(context.layout.transcript_kk_path)
    context.store.write_manifest(context.manifest)

    print(
        f"[pipeline] Translating subtitles to {context.config.subtitle_language}: "
        f"segments={len(transcript.segments)}"
    )
    transcript_zh = service.to_chinese_subtitles(transcript)
    write_srt(context.layout.subtitles_zh_path, transcript_zh)
    print(f"[pipeline] Wrote subtitle file to {context.layout.subtitles_zh_path}")
    context.manifest.steps["subtitle"] = "done"
    context.manifest.artifacts["subtitles_zh"] = str(context.layout.subtitles_zh_path)
    context.store.write_manifest(context.manifest)
    return transcript_kk, transcript_zh


def run_tts_compose_and_mux(
    context: PipelineContext, transcript_kk: TranscriptDocument
) -> TranscriptDocument:
    tts_service = build_tts_service(context.config)
    default_voice_name = context.config.tts.gemini_voice_names.get(
        "SPEAKER_00",
        context.config.tts.voice,
    )
    speaker_voice_count = len(context.config.tts.gemini_voice_names)
    print(
        f"[pipeline] Starting TTS synthesis: segments={len(transcript_kk.segments)} "
        f"default_voice={default_voice_name} speaker_voices={speaker_voice_count}"
    )
    transcript_with_tts = tts_service.run(
        transcript_kk,
        tts_dir=context.layout.tts_dir,
        raw_tts_dir=context.layout.tts_raw_dir,
        voice=default_voice_name,
        voices_by_speaker=context.config.tts.gemini_voice_names,
    )

    print("[pipeline] Preparing synthesized segments for timeline composition")
    compose_service = AudioComposeService(context.config.tts_alignment)
    prepared_transcript = compose_service.prepare_transcript(transcript_with_tts)
    duration_summary = summarize_duration_statuses(prepared_transcript)
    context.manifest.duration_summary = DurationSummary.model_validate(duration_summary)
    context.store.write_transcript_kk_with_tts(prepared_transcript)
    context.manifest.steps["tts"] = "done"
    context.manifest.artifacts["tts_dir"] = str(context.layout.tts_dir)
    context.manifest.artifacts["tts_raw_dir"] = str(context.layout.tts_raw_dir)
    manual_review_segments = [
        build_manual_review_segment_row(
            segment.model_copy(
                update={
                    "next_segment_for_manual_review": prepared_transcript.segments[index + 1]
                    if index + 1 < len(prepared_transcript.segments)
                    else None,
                    "alignment_for_manual_review": context.config.tts_alignment,
                }
            )
        )
        for index, segment in enumerate(prepared_transcript.segments)
        if segment.duration_status == "manual_review"
    ]
    context.store.write_manual_review_segments(manual_review_segments)
    context.manifest.artifacts["manual_review_segments"] = str(
        context.layout.manual_review_segments_path
    )
    context.store.write_manifest(context.manifest)
    print(
        "[pipeline] TTS summary: "
        f"total={duration_summary['total_segments']} "
        f"preferred={duration_summary['preferred_count']} "
        f"acceptable={duration_summary['acceptable_count']} "
        f"too_short={duration_summary['too_short_count']} "
        f"too_long={duration_summary['too_long_count']} "
        f"manual_review={duration_summary['manual_review_count']} "
        f"avg_abs_error={duration_summary['avg_abs_duration_error']:.3f} "
        f"time_stretch={duration_summary['time_stretch_applied_count']}"
    )

    print(f"[pipeline] Composing dub audio to {context.layout.dub_audio_path}")
    compose_service.compose(prepared_transcript, context.layout.dub_audio_path)
    print(f"[pipeline] Wrote dub audio to {context.layout.dub_audio_path}")
    context.manifest.steps["compose_audio"] = "done"
    context.manifest.artifacts["dub_audio"] = str(context.layout.dub_audio_path)
    context.store.write_manifest(context.manifest)

    mux_service = VideoMuxService()
    subtitle_mode = context.config.video.subtitle_mode
    print(
        f"[pipeline] Muxing final video to {context.layout.final_video_path}: "
        f"subtitle_mode={subtitle_mode}"
    )
    input_video = require_manifest_input_video(context.manifest.input_video)
    if subtitle_mode == "hard":
        mux_service.mux_hard_subtitle(
            input_video=input_video,
            dub_audio=context.layout.dub_audio_path,
            subtitle_srt=context.layout.subtitles_zh_path,
            output_video=context.layout.final_video_path,
        )
    else:
        mux_service.mux_soft_subtitle(
            input_video=input_video,
            dub_audio=context.layout.dub_audio_path,
            subtitle_srt=context.layout.subtitles_zh_path,
            output_video=context.layout.final_video_path,
        )
    print(f"[pipeline] Wrote final video to {context.layout.final_video_path}")
    context.manifest.steps["mux_video"] = "done"
    context.manifest.artifacts["final_video"] = str(context.layout.final_video_path)
    context.manifest.artifacts["subtitle_mode"] = subtitle_mode
    context.store.write_manifest(context.manifest)
    return prepared_transcript
