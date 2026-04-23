from pathlib import Path

from video_dub.models.manifest import DurationSummary, RunManifest


def test_manifest_defaults() -> None:
    manifest = RunManifest(job_id="job-1", input_video=Path("input.mp4"))
    assert manifest.steps["extract_audio"] == "pending"
    assert manifest.target_language == "kk"


def test_manifest_can_track_artifacts() -> None:
    manifest = RunManifest(job_id="job-1", input_video=Path("input.mp4"))
    manifest.steps["extract_audio"] = "done"
    manifest.artifacts["source_audio"] = "runs/job-1/artifacts/source_audio.wav"
    assert manifest.steps["extract_audio"] == "done"
    assert manifest.artifacts["source_audio"].endswith("source_audio.wav")


def test_duration_summary_tracks_extended_alignment_metrics() -> None:
    summary = DurationSummary(
        total_segments=5,
        preferred_count=1,
        acceptable_count=2,
        too_short_count=1,
        too_long_count=0,
        manual_review_count=1,
        avg_abs_duration_error=0.12,
        time_stretch_applied_count=1,
        trim_trailing_silence_applied_count=1,
        pad_silence_applied_count=2,
    )

    manifest = RunManifest(job_id="job-1", input_video=Path("input.mp4"), duration_summary=summary)

    assert manifest.duration_summary.too_short_count == 1
    assert manifest.duration_summary.manual_review_count == 1
    assert manifest.duration_summary.avg_abs_duration_error == 0.12
    assert manifest.duration_summary.time_stretch_applied_count == 1
