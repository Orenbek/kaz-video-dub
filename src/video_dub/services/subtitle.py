from __future__ import annotations

from pathlib import Path

import srt

from video_dub.models.transcript import TranscriptDocument


def render_srt(transcript: TranscriptDocument) -> str:
    subtitles = []
    for index, segment in enumerate(transcript.segments, start=1):
        content = segment.subtitle_zh or segment.text_en
        subtitles.append(
            srt.Subtitle(
                index=index,
                start=srt.timedelta(seconds=segment.start),
                end=srt.timedelta(seconds=segment.end),
                content=content,
            )
        )
    return srt.compose(subtitles)


def write_srt(path: Path, transcript: TranscriptDocument) -> None:
    path.write_text(render_srt(transcript), encoding="utf-8")
