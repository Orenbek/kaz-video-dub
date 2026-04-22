from pathlib import Path

from video_dub.config import AppConfig
from video_dub.pipeline import initialize_run


def test_initialize_run_copies_input_and_writes_manifest(tmp_path: Path) -> None:
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake-video")

    config = AppConfig(run_root=tmp_path / "runs")
    context = initialize_run(config, input_video, job_id="job-1")

    assert context.layout.run_dir == tmp_path / "runs" / "job-1"
    assert Path(context.manifest.input_video).exists()
    assert context.layout.manifest_path.exists()
    assert context.layout.source_audio_path.parent.exists()
    assert context.manifest.duration_summary.total_segments == 0
