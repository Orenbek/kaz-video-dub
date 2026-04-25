from pathlib import Path

from video_dub.ffmpeg.commands import build_compose_segment_filter
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


def test_video_mux_builds_hard_subtitle_command() -> None:
    service = VideoMuxService()
    command = service.build_hard_subtitle_command(
        input_video=Path("input.mp4"),
        dub_audio=Path("dub_kk.wav"),
        subtitle_srt=Path("subtitles.zh.srt"),
        output_video=Path("final.mp4"),
    )

    assert '"input.mp4"' in command
    assert '"dub_kk.wav"' in command
    assert "subtitles=subtitles.zh.srt" in command
    assert "-c:v libx264" in command
    assert "-c:a aac" in command
    assert "-sn" in command
    assert "-c:s mov_text" not in command


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
                raw_tts_path=Path("artifacts/tts_raw/seg_0001.wav"),
                target_duration=1.0,
                initial_tts_duration=0.8,
                tts_duration=0.8,
                duration_status="acceptable",
                duration_error_seconds=-0.2,
                correction_actions=["pad_silence"],
                has_timeline_collision=False,
            )
        ],
    )

    segment = transcript.segments[0]
    assert segment.tts_path == Path("artifacts/tts/seg_0001.wav")
    assert segment.raw_tts_path == Path("artifacts/tts_raw/seg_0001.wav")
    assert segment.target_duration == 1.0
    assert segment.initial_tts_duration == 0.8
    assert segment.tts_duration == 0.8
    assert segment.duration_status == "acceptable"
    assert segment.duration_error_seconds == -0.2
    assert segment.correction_actions == ["pad_silence"]
    assert segment.has_timeline_collision is False


def test_compose_filter_pads_early_segment_with_silence() -> None:
    segment = Segment(
        id="seg_0001",
        start=0.5,
        end=1.5,
        text_en="Hello",
        tts_path=Path("artifacts/tts/seg_0001.wav"),
        target_duration=1.0,
        tts_duration=0.8,
    )

    filter_part = build_compose_segment_filter(segment, 0)

    assert "apad=pad_dur=200ms" in filter_part
    assert "adelay=500|500" in filter_part
