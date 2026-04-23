import json
from pathlib import Path

from typer.testing import CliRunner

from video_dub.cli import app
from video_dub.config import AppConfig
from video_dub.models.manifest import RunManifest
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.pipeline import (
    build_manual_review_segment_row,
    initialize_run,
    require_manifest_input_video,
    run_tts_compose_and_mux,
)
from video_dub.services.repair import apply_segment_repairs, rebuild_run_outputs
from video_dub.storage.artifacts import ArtifactStore
from video_dub.storage.run_layout import RunLayout

runner = CliRunner()


def test_initialize_run_copies_input_and_writes_manifest(tmp_path: Path) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")

    config = AppConfig(run_root=tmp_path / "runs")
    context = initialize_run(config, input_video, job_id="job-1")

    assert context.layout.run_dir == tmp_path / "runs" / "job-1"
    assert require_manifest_input_video(context.manifest.input_video).exists()
    assert context.layout.manifest_path.exists()
    assert context.layout.source_audio_path.parent.exists()
    assert context.manifest.duration_summary.total_segments == 0


def test_run_layout_exposes_manual_review_paths(tmp_path: Path) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")

    config = AppConfig(run_root=tmp_path / "runs")
    context = initialize_run(config, input_video, job_id="job-2")

    assert context.layout.tts_raw_dir.exists()
    assert context.layout.manual_review_segments_path.parent == context.layout.run_dir


def test_run_tts_compose_and_mux_writes_manual_review_artifact(tmp_path: Path, monkeypatch) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")
    context = initialize_run(AppConfig(run_root=tmp_path / "runs"), input_video, job_id="job-3")

    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg_1", start=0.0, end=1.0, text_en="Hello", text_kk="Сәлем")],
    )

    prepared = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg_1",
                start=0.0,
                end=1.0,
                text_en="Hello",
                text_kk="Сәлем",
                raw_tts_path=Path("artifacts/tts_raw/seg_1.wav"),
                tts_path=Path("artifacts/tts/seg_1.wav"),
                target_duration=1.0,
                initial_tts_duration=1.4,
                tts_duration=1.4,
                duration_status="manual_review",
                duration_error_seconds=0.4,
                correction_actions=[],
                has_timeline_collision=True,
            )
        ],
    )

    class FakeTTSService:
        def run(self, transcript_kk, tts_dir, voice, raw_tts_dir=None):
            return prepared

    class FakeComposeService:
        def __init__(self, alignment):
            self.alignment = alignment

        def prepare_transcript(self, transcript_with_tts):
            return transcript_with_tts

        def compose(self, transcript_with_tts, output_path):
            output_path.write_bytes(b"dub")
            return output_path

    class FakeMuxService:
        def mux_soft_subtitle(self, input_video, dub_audio, subtitle_srt, output_video):
            output_video.write_bytes(b"video")
            return output_video

    monkeypatch.setattr("video_dub.pipeline.build_tts_service", lambda config: FakeTTSService())
    monkeypatch.setattr("video_dub.pipeline.AudioComposeService", FakeComposeService)
    monkeypatch.setattr("video_dub.pipeline.VideoMuxService", FakeMuxService)
    context.layout.subtitles_zh_path.write_text("stub", encoding="utf-8")

    result = run_tts_compose_and_mux(context, transcript)

    rows = json.loads(context.layout.manual_review_segments_path.read_text(encoding="utf-8"))
    assert result.segments[0].duration_status == "manual_review"
    assert rows == [
        {
            "segment_id": "seg_1",
            "start": 0.0,
            "end": 1.0,
            "text_en": "Hello",
            "text_kk": "Сәлем",
            "target_duration": 1.0,
            "initial_tts_duration": 1.4,
            "tts_duration": 1.4,
            "duration_error_seconds": 0.4,
            "has_timeline_collision": True,
            "timeline_overhang_seconds": None,
            "duration_status": "manual_review",
            "manual_review_reason": "timeline_collision_unresolved",
            "correction_actions": [],
            "time_stretch_ratio": None,
            "raw_tts_path": "artifacts/tts_raw/seg_1.wav",
            "tts_path": "artifacts/tts/seg_1.wav",
        }
    ]


def test_run_tts_compose_and_mux_writes_overhang_for_unresolved_collision_with_next_segment(
    tmp_path: Path, monkeypatch
) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")
    config = AppConfig(run_root=tmp_path / "runs")
    config.tts_alignment = config.tts_alignment.model_copy(update={"allow_minor_overhang_seconds": 0.1})
    context = initialize_run(config, input_video, job_id="job-overhang")

    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(id="seg_1", start=0.0, end=1.0, text_en="Hello", text_kk="Сәлем"),
            Segment(id="seg_2", start=1.0, end=2.0, text_en="World", text_kk="Әлем"),
        ],
    )

    prepared = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg_1",
                start=0.0,
                end=1.0,
                text_en="Hello",
                text_kk="Сәлем",
                raw_tts_path=Path("artifacts/tts_raw/seg_1.wav"),
                tts_path=Path("artifacts/tts/seg_1.wav"),
                target_duration=1.0,
                initial_tts_duration=1.4,
                tts_duration=1.25,
                duration_status="manual_review",
                duration_error_seconds=0.25,
                correction_actions=["trim_trailing_silence"],
                has_timeline_collision=True,
            ),
            Segment(
                id="seg_2",
                start=1.0,
                end=2.0,
                text_en="World",
                text_kk="Әлем",
                raw_tts_path=Path("artifacts/tts_raw/seg_2.wav"),
                tts_path=Path("artifacts/tts/seg_2.wav"),
                target_duration=1.0,
                initial_tts_duration=1.0,
                tts_duration=1.0,
                duration_status="preferred",
                duration_error_seconds=0.0,
                correction_actions=[],
                has_timeline_collision=False,
            ),
        ],
    )

    class FakeTTSService:
        def run(self, transcript_kk, tts_dir, voice, raw_tts_dir=None):
            return prepared

    class FakeComposeService:
        def __init__(self, alignment):
            self.alignment = alignment

        def prepare_transcript(self, transcript_with_tts):
            return transcript_with_tts

        def compose(self, transcript_with_tts, output_path):
            output_path.write_bytes(b"dub")
            return output_path

    class FakeMuxService:
        def mux_soft_subtitle(self, input_video, dub_audio, subtitle_srt, output_video):
            output_video.write_bytes(b"video")
            return output_video

    monkeypatch.setattr("video_dub.pipeline.build_tts_service", lambda config: FakeTTSService())
    monkeypatch.setattr("video_dub.pipeline.AudioComposeService", FakeComposeService)
    monkeypatch.setattr("video_dub.pipeline.VideoMuxService", FakeMuxService)
    context.layout.subtitles_zh_path.write_text("stub", encoding="utf-8")

    run_tts_compose_and_mux(context, transcript)

    rows = json.loads(context.layout.manual_review_segments_path.read_text(encoding="utf-8"))
    assert rows[0]["segment_id"] == "seg_1"
    assert rows[0]["timeline_overhang_seconds"] == 0.15
    assert rows[0]["manual_review_reason"] == "timeline_collision_unresolved"


def test_build_manual_review_segment_row_adds_reason_and_overhang() -> None:
    segment = Segment(
        id="seg_2",
        start=0.0,
        end=1.0,
        text_en="Hi",
        text_kk="Сәлем",
        target_duration=1.0,
        initial_tts_duration=1.3,
        tts_duration=1.25,
        duration_error_seconds=0.25,
        duration_status="manual_review",
        has_timeline_collision=True,
        correction_actions=["trim_trailing_silence"],
    )

    row = build_manual_review_segment_row(
        segment.model_copy(
            update={
                "next_segment_for_manual_review": Segment(
                    id="seg_3", start=1.0, end=2.0, text_en="Next", text_kk="Келесі"
                ),
                "alignment_for_manual_review": AppConfig().tts_alignment.model_copy(
                    update={"allow_minor_overhang_seconds": 0.1}
                ),
            }
        )
    )

    assert row["manual_review_reason"] == "timeline_collision_unresolved"
    assert row["timeline_overhang_seconds"] == 0.15


def test_run_tts_compose_and_mux_skips_duration_control_when_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")
    config = AppConfig(run_root=tmp_path / "runs")
    config.tts_alignment = config.tts_alignment.model_copy(update={"enabled": False})
    context = initialize_run(config, input_video, job_id="job-disabled")
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[Segment(id="seg_1", start=0.0, end=1.0, text_en="Hello", text_kk="Сәлем")],
    )

    class FakeTTSService:
        def run(self, transcript_kk, tts_dir, voice, raw_tts_dir=None):
            output_path = tts_dir / "seg_1.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"tts")
            return transcript_kk.model_copy(
                update={
                    "segments": [
                        transcript_kk.segments[0].model_copy(
                            update={
                                "tts_path": output_path,
                                "raw_tts_path": output_path,
                            }
                        )
                    ]
                }
            )

    class FakeComposeService:
        def __init__(self, alignment):
            self.alignment = alignment

        def prepare_transcript(self, transcript_with_tts):
            return transcript_with_tts

        def compose(self, transcript_with_tts, output_path):
            output_path.write_bytes(b"dub")
            return output_path

    class FakeMuxService:
        def mux_soft_subtitle(self, input_video, dub_audio, subtitle_srt, output_video):
            output_video.write_bytes(b"video")
            return output_video

    monkeypatch.setattr("video_dub.pipeline.build_tts_service", lambda config: FakeTTSService())
    monkeypatch.setattr("video_dub.pipeline.AudioComposeService", FakeComposeService)
    monkeypatch.setattr("video_dub.pipeline.VideoMuxService", FakeMuxService)
    context.layout.subtitles_zh_path.write_text("stub", encoding="utf-8")

    result = run_tts_compose_and_mux(context, transcript)

    assert result.segments[0].duration_status is None
    assert result.segments[0].tts_duration is None
    assert json.loads(context.layout.manual_review_segments_path.read_text(encoding="utf-8")) == []


def test_repair_export_cli_writes_manual_review_rows(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "job-1"
    run_dir.mkdir(parents=True)
    transcript_path = run_dir / "transcript.kk.json"
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg_3",
                start=0.0,
                end=1.0,
                text_en="Hello",
                text_kk="Сәлем",
                duration_status="manual_review",
                target_duration=1.0,
                tts_duration=1.3,
                duration_error_seconds=0.3,
                has_timeline_collision=True,
            )
        ],
    )
    transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    output_path = run_dir / "repair.json"

    result = runner.invoke(
        app, ["repair-export", "--run-dir", str(run_dir), "--output", str(output_path)]
    )

    assert result.exit_code == 0
    rows = json.loads(output_path.read_text(encoding="utf-8"))
    assert rows[0]["segment_id"] == "seg_3"
    assert rows[0]["manual_review_reason"] == "timeline_collision_unresolved"


def test_apply_segment_repairs_updates_only_requested_segment(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "runs" / "job-2"
    layout = RunLayout(run_dir)
    layout.ensure()
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg_1",
                start=0.0,
                end=1.0,
                text_en="Hello",
                text_kk="old",
                duration_status="manual_review",
            ),
            Segment(
                id="seg_2",
                start=1.2,
                end=2.0,
                text_en="World",
                text_kk="keep",
                duration_status="acceptable",
            ),
        ],
    )
    config = AppConfig(run_root=tmp_path / "runs")
    store = ArtifactStore(layout)

    class FakeTTSService:
        def process_segment(self, segment, next_segment, tts_dir, raw_tts_dir, voice):
            return segment.model_copy(
                update={
                    "tts_path": tts_dir / f"{segment.id}.wav",
                    "raw_tts_path": raw_tts_dir / f"{segment.id}.wav",
                    "tts_duration": 0.95,
                    "target_duration": 1.0,
                    "initial_tts_duration": 1.1,
                    "duration_status": "acceptable",
                    "duration_error_seconds": -0.05,
                    "has_timeline_collision": False,
                }
            )

    class FakeComposeService:
        def __init__(self, alignment):
            self.alignment = alignment

        def prepare_segment(self, segment, next_segment):
            return segment

    monkeypatch.setattr(
        "video_dub.services.repair.build_tts_service", lambda config: FakeTTSService()
    )
    monkeypatch.setattr("video_dub.services.repair.AudioComposeService", FakeComposeService)
    monkeypatch.setattr(store, "write_transcript_kk_with_tts", lambda transcript: None)

    updated = apply_segment_repairs(
        run_dir=run_dir,
        transcript=transcript,
        repair_rows=[{"segment_id": "seg_1", "text_kk": "new text"}],
        config=config,
        store=store,
    )

    assert updated.segments[0].text_kk == "new text"
    assert updated.segments[0].duration_status == "acceptable"
    assert updated.segments[1].text_kk == "keep"


def test_rebuild_run_outputs_refreshes_manual_review_artifact(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "runs" / "job-4"
    layout = RunLayout(run_dir)
    layout.ensure()
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")
    layout.subtitles_zh_path.write_text("stub", encoding="utf-8")
    manifest = RunManifest(job_id="job-4", input_video=str(input_video))
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="kk",
        segments=[
            Segment(
                id="seg_9",
                start=0.0,
                end=1.0,
                text_en="A",
                text_kk="B",
                duration_status="manual_review",
                tts_duration=1.2,
                target_duration=1.0,
                duration_error_seconds=0.2,
                has_timeline_collision=True,
            )
        ],
    )

    class FakeComposeService:
        def __init__(self, alignment):
            self.alignment = alignment

        def compose(self, transcript, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"dub")
            return output_path

    class FakeMuxService:
        def mux_soft_subtitle(self, input_video, dub_audio, subtitle_srt, output_video):
            output_video.write_bytes(b"video")
            return output_video

    monkeypatch.setattr("video_dub.services.repair.AudioComposeService", FakeComposeService)
    monkeypatch.setattr("video_dub.services.repair.VideoMuxService", FakeMuxService)
    store = ArtifactStore(layout)
    monkeypatch.setattr(store, "write_manifest", lambda manifest: None)

    config = AppConfig(run_root=tmp_path / "runs")
    manual_rows = rebuild_run_outputs(
        run_dir=run_dir,
        transcript=transcript,
        manifest=manifest,
        config=config,
        store=store,
    )

    assert manual_rows[0]["segment_id"] == "seg_9"
    assert manual_rows[0]["manual_review_reason"] == "timeline_collision_unresolved"
