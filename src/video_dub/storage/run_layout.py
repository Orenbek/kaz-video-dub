from __future__ import annotations

from pathlib import Path


class RunLayout:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.input_dir = run_dir / "input"
        self.artifacts_dir = run_dir / "artifacts"
        self.tts_dir = self.artifacts_dir / "tts"
        self.tts_raw_dir = self.artifacts_dir / "tts_raw"
        self.manifest_path = run_dir / "manifest.json"
        self.manual_review_segments_path = run_dir / "manual_review_segments.json"
        self.source_audio_path = self.artifacts_dir / "source_audio.wav"
        self.transcript_en_path = run_dir / "transcript.en.json"
        self.transcript_en_diarized_path = run_dir / "transcript.en.diarized.json"
        self.transcript_kk_path = run_dir / "transcript.kk.json"
        self.subtitles_zh_path = run_dir / "subtitles.zh.srt"
        self.dub_audio_path = run_dir / "dub_kk.wav"
        self.final_video_path = run_dir / "final.mp4"

    def ensure(self) -> None:
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.tts_dir.mkdir(parents=True, exist_ok=True)
        self.tts_raw_dir.mkdir(parents=True, exist_ok=True)
