from pathlib import Path

from video_dub.models.segment import DiarizationSpan, Segment
from video_dub.models.transcript import TranscriptDocument
from video_dub.services.diarization import DiarizationService


class FakeProvider:
    def __init__(self, spans: list[DiarizationSpan]) -> None:
        self.spans = spans
        self.audio_paths: list[Path] = []

    def diarize(self, audio_path: Path) -> list[DiarizationSpan]:
        self.audio_paths.append(audio_path)
        return self.spans


def test_diarization_service_assigns_segment_speaker_by_largest_overlap() -> None:
    audio_path = Path("source.wav")
    transcript = TranscriptDocument(
        source_audio_path=audio_path,
        language="en",
        segments=[
            Segment(id="seg_0001", start=0.0, end=3.0, text_en="Hello"),
            Segment(id="seg_0002", start=3.0, end=5.0, text_en="World"),
            Segment(id="seg_0003", start=8.0, end=9.0, text_en="No overlap"),
        ],
    )
    provider = FakeProvider(
        [
            DiarizationSpan(start=0.0, end=1.0, speaker="SPEAKER_00"),
            DiarizationSpan(start=1.0, end=4.5, speaker="SPEAKER_01"),
        ]
    )

    diarized = DiarizationService(provider).run(transcript, audio_path)

    assert provider.audio_paths == [audio_path]
    assert [segment.speaker for segment in diarized.segments] == [
        "SPEAKER_01",
        "SPEAKER_01",
        None,
    ]
    assert diarized.metadata["diarization"] == {
        "provider": "pyannote",
        "span_count": 2,
        "speaker_count": 2,
        "assigned_segment_count": 2,
    }


def test_diarization_service_tie_breaks_by_speaker_label() -> None:
    segment = Segment(id="seg_0001", start=0.0, end=2.0, text_en="Hello")
    spans = [
        DiarizationSpan(start=1.0, end=2.0, speaker="SPEAKER_01"),
        DiarizationSpan(start=0.0, end=1.0, speaker="SPEAKER_00"),
    ]

    speaker = DiarizationService(FakeProvider([])).assign_speaker(segment, spans)

    assert speaker == "SPEAKER_00"
