from types import SimpleNamespace

from video_dub.providers.pyannote_provider import PyannoteProvider


class FakeDiarizationFrame:
    def itertuples(self, index=False):
        assert index is False
        yield SimpleNamespace(start=5.0, end=6.0, speaker="SPEAKER_01")
        yield SimpleNamespace(start=1.0, end=2.0, speaker="SPEAKER_00")
        yield SimpleNamespace(start=3.0, end=3.0, speaker="SPEAKER_02")


def test_pyannote_provider_builds_sorted_positive_duration_spans() -> None:
    spans = PyannoteProvider()._build_spans(FakeDiarizationFrame())

    assert [(span.start, span.end, span.speaker) for span in spans] == [
        (1.0, 2.0, "SPEAKER_00"),
        (5.0, 6.0, "SPEAKER_01"),
    ]
