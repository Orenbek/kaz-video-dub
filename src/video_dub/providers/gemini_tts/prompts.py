from __future__ import annotations

from video_dub.providers.gemini_tts.speech_rate import build_segment_timing_notes

DEFAULT_GEMINI_TTS_PROMPT_PREAMBLE = """\
Synthesize natural spoken Kazakh audio from the transcript below.
Read only the transcript text; do not read these instructions, labels, or section headings.

### DIRECTOR'S NOTES
Language: Kazakh (kk-KZ).
Accent: Native Kazakh speaker from Almaty, Kazakhstan.
Reference: Kazakh-language TV or radio interviewer.
Avoid English, British, American, or Russian accented pronunciation.
Style: Natural documentary/interview dubbing. Confident, conversational, and clear.
Pacing: Brisk and compact for video dubbing. Avoid long pauses, extra breaths, or added words.
Delivery: Preserve proper nouns naturally. Do not translate, explain, summarize, or embellish.

### TRANSCRIPT"""


def insert_timing_notes_before_transcript(prompt_preamble: str, timing_notes: str) -> str:
    transcript_heading = "### TRANSCRIPT"
    if transcript_heading not in prompt_preamble:
        return f"{prompt_preamble}\n\n{timing_notes}\n\n{transcript_heading}"

    before_transcript, separator, after_transcript = prompt_preamble.rpartition(transcript_heading)
    return (
        f"{before_transcript.rstrip()}\n\n{timing_notes}\n\n{separator}{after_transcript}"
    ).rstrip()


def build_tts_prompt(
    *,
    text: str,
    prompt_preamble: str,
    target_duration_seconds: float | None,
    language: str,
) -> str:
    prompt = prompt_preamble.rstrip()
    timing_notes = build_segment_timing_notes(
        text=text,
        target_duration_seconds=target_duration_seconds,
        language=language,
    )
    if timing_notes:
        prompt = insert_timing_notes_before_transcript(prompt, timing_notes)
    return f"{prompt}\n{text.strip()}"
