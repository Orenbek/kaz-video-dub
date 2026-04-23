import wave
from pathlib import Path

from video_dub.models.segment import Segment
from video_dub.providers.gemini_tts_provider import GeminiTTSConfig, GeminiTTSProvider


def test_stub_tts_writes_wav_file(tmp_path: Path) -> None:
    provider = GeminiTTSProvider(GeminiTTSConfig(use_stub=True, sample_rate=24000))
    segment = Segment(id="seg_0001", start=0.0, end=1.0, text_en="Hello", text_kk="Сәлем")
    output_path = tmp_path / "seg_0001.wav"

    result = provider.synthesize_segment(segment, output_path, voice="kazakh-default")

    assert result.exists()
    with wave.open(str(result), "rb") as wav_file:
        assert wav_file.getframerate() == 24000
        assert wav_file.getnchannels() == 1
