from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.subtitle import render_srt


def test_render_srt_uses_subtitle_text() -> None:
    transcript = TranscriptDocument(
        source_audio_path=Path("source.wav"),
        language="en",
        segments=[
            Segment(
                id="seg_1",
                start=0.0,
                end=2.0,
                text_en="Hello",
                subtitle_zh="你好",
            )
        ],
    )
    rendered = render_srt(transcript)
    assert "你好" in rendered
    assert "00:00:00,000 --> 00:00:02,000" in rendered
