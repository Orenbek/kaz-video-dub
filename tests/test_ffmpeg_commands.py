from pathlib import Path

from video_dub.ffmpeg.commands import compose_dub_audio_command
from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument


def test_compose_dub_audio_command_contains_inputs_and_amix() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[
            Segment(
                id="seg_0001",
                start=0.5,
                end=1.5,
                text_en="Hello",
                tts_path=Path("artifacts/tts/seg_0001.wav"),
            ),
            Segment(
                id="seg_0002",
                start=2.0,
                end=3.0,
                text_en="World",
                tts_path=Path("artifacts/tts/seg_0002.wav"),
            ),
        ],
    )

    command = compose_dub_audio_command(transcript, Path("dub_kk.wav"))

    assert '"artifacts/tts/seg_0001.wav"' in command
    assert '"artifacts/tts/seg_0002.wav"' in command
    assert "adelay=500|500" in command
    assert "adelay=2000|2000" in command
    assert "amix=inputs=2" in command
