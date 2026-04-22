from pathlib import Path

from video_dub.storage.run_layout import RunLayout


def test_run_layout_paths(tmp_path: Path) -> None:
    layout = RunLayout(tmp_path / "job-1")
    layout.ensure()
    assert layout.tts_dir.exists()
    assert layout.source_audio_path.name == "source_audio.wav"
