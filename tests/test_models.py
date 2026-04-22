from video_dub.models.segment import Segment


def test_segment_duration() -> None:
    segment = Segment(id="seg_0001", start=1.5, end=4.0, text_en="hello")
    assert segment.duration == 2.5
