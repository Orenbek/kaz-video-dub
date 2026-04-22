from pathlib import Path

from video_dub.models.manifest import RunManifest


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
