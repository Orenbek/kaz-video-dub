from pathlib import Path

from video_dub.models.manifest import RunManifest


def test_manifest_defaults() -> None:
    manifest = RunManifest(job_id="job-1", input_video=Path("input.mp4"))
    assert manifest.steps["extract_audio"] == "pending"
    assert manifest.target_language == "kk"
