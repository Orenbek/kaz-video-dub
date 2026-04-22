from pathlib import Path

from video_dub.config import AppConfig
from video_dub.services.audio_extract import AudioExtractor


def test_audio_extractor_builds_ffmpeg_command() -> None:
    config = AppConfig()
    extractor = AudioExtractor(config)

    command = extractor.build_command(Path("input.mp4"), Path("output.wav"))

    assert "ffmpeg -y" in command
    assert '"input.mp4"' in command
    assert '"output.wav"' in command
    assert "-ar 16000" in command
    assert "-ac 1" in command
