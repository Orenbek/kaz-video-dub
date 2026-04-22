from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.video_mux import VideoMuxService


def test_video_mux_builds_soft_subtitle_command() -> None:
    service = VideoMuxService()
    command = service.build_soft_subtitle_command(
        input_video=Path("input.mp4"),
        dub_audio=Path("dub_kk.wav"),
        subtitle_srt=Path("subtitles.zh.srt"),
        output_video=Path("final.mp4"),
    )

    assert '"input.mp4"' in command
    assert '"dub_kk.wav"' in command
    assert '"subtitles.zh.srt"' in command
    assert "-c:s mov_text" in command


def test_transcript_can_store_tts_metadata() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[
            Segment(
                id="seg_0001",
                start=0.0,
                end=1.0,
                text_en="Hello",
                text_kk="Сәлем",
                tts_path=Path("artifacts/tts/seg_0001.wav"),
                tts_duration=0.8,
            )
        ],
    )

    assert transcript.segments[0].tts_path == Path("artifacts/tts/seg_0001.wav")
    assert transcript.segments[0].tts_duration == 0.8
