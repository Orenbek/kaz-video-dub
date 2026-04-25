# Gemini TTS voices

Gemini TTS uses a prebuilt `voice_name` inside `speech_config.voice_config`.
Configure the fallback voice with `tts.voice`:

```yaml
tts:
  use_stub: false
  model_name: gemini-3.1-flash-tts-preview
  voice: Kore
```

For diarized material, configure per-speaker voices with
`tts.gemini_voice_names`. Speaker labels come from the diarization stage:

```yaml
tts:
  voice: Kore
  gemini_voice_names:
    SPEAKER_00: Kore
    SPEAKER_01: Charon
```

Segments whose speaker is missing or absent from the map use
`tts.gemini_voice_names.SPEAKER_00`, then fall back to `tts.voice`.

You can compare these speaker voices in Google AI Studio:
https://aistudio.google.com/generate-speech

## Available voices

The Gemini API lists voice names and styles, but does not expose a gender
field in the API. The `Sex` column below is a practical perceived-voice label
for voice selection; confirm final choices by listening in AI Studio.

| Voice name | Sex | Style |
| --- | --- | --- |
| Zephyr | Female / 女 | Bright / 明亮 |
| Puck | Male / 男 | Upbeat / 欢快 |
| Charon | Male / 男 | Informative / 信息丰富 |
| Kore | Female / 女 | Firm / 坚定 |
| Fenrir | Male / 男 | Excitable / 兴奋 |
| Leda | Female / 女 | Youthful / 青春 |
| Orus | Male / 男 | Firm / 坚定 |
| Aoede | Female / 女 | Breezy / 轻快 |
| Callirrhoe | Female / 女 | Easy-going / 随和 |
| Autonoe | Female / 女 | Bright / 明亮 |
| Enceladus | Male / 男 | Breathy / 气声 |
| Iapetus | Male / 男 | Clear / 清晰 |
| Umbriel | Male / 男 | Easy-going / 轻松自在 |
| Algieba | Male / 男 | Smooth / 平滑 |
| Despina | Female / 女 | Smooth / 平滑 |
| Erinome | Female / 女 | Clear / 清晰 |
| Algenib | Male / 男 | Gravelly / 沙哑 |
| Rasalgethi | Male / 男 | Informative / 信息丰富 |
| Laomedeia | Female / 女 | Upbeat / 欢快 |
| Achernar | Female / 女 | Soft / 柔和 |
| Alnilam | Male / 男 | Firm / 坚定 |
| Schedar | Male / 男 | Even / 平稳 |
| Gacrux | Female / 女 | Mature / 成熟 |
| Pulcherrima | Male / 男 | Forward / 直率 |
| Achird | Male / 男 | Friendly / 友好 |
| Zubenelgenubi | Male / 男 | Casual / 随意 |
| Vindemiatrix | Female / 女 | Gentle / 温柔 |
| Sadachbia | Male / 男 | Lively / 活泼 |
| Sadaltager | Male / 男 | Knowledgeable / 知识渊博 |
| Sulafat | Female / 女 | Warm / 温暖 |

## Selection notes

For interview dubbing, start with `Kore`, `Alnilam`, `Schedar`, or `Charon`.
They tend to be steadier choices than highly expressive voices such as `Fenrir`.

For short interjections, voices with long natural tails can still exceed the
source timing window. If a voice creates many `manual_review` segments, try a
firmer or more even voice before rewriting translations.

## Prompting for Kazakh dubbing

The project uses a Gemini TTS prompt preamble modeled on Google's prompting
guide: it gives a clear synthesis instruction, separates `DIRECTOR'S NOTES`
from `TRANSCRIPT`, and describes the desired accent, style, and pacing.

The default preamble asks for:

- native Kazakh pronunciation from Almaty, Kazakhstan
- a Kazakh-language TV/radio interviewer reference
- no English, British, American, or Russian accented pronunciation
- natural documentary/interview dubbing
- brisk, compact pacing for video dubbing
- no translation, explanation, added words, or section heading narration

Override it with `tts.gemini_prompt_preamble` when comparing variants:

```yaml
tts:
  voice: Alnilam
  gemini_prompt_preamble: |
    Synthesize natural spoken Kazakh audio from the transcript below.
    Read only the transcript text; do not read these instructions.

    ### DIRECTOR'S NOTES
    Language: Kazakh (kk-KZ).
    Accent: Native Kazakh speaker from Almaty, Kazakhstan.
    Style: Neutral interview dubbing, calm and direct.
    Pacing: Brisk and compact.

    ### TRANSCRIPT
```

As of the current Gemini TTS documentation, Kazakh is not listed in the
official supported-language table. Treat prompt tuning here as a quality
experiment, not a guarantee that Gemini TTS can produce native-quality Kazakh.

## Segment timing guidance

Each Gemini TTS segment prompt also receives a generated `SEGMENT TIMING`
section before the transcript. The provider estimates the required speaking
pace from the segment target duration and transcript length:

- Chinese (`zh`) counts Han characters.
- Kazakh (`kk`) counts whitespace-separated words.
- Other languages default to whitespace-separated words.

When the estimated pace is unusually fast, the prompt asks for brisk, compact
dubbing with minimal pauses. When the text is sparse for the available time,
the prompt asks for natural delivery without stretched syllables, extra pauses,
or added words.

The current Kazakh word-rate thresholds are intentionally fixed in code. They
are calibrated against common clear-speech and conversational ranges: roughly
125-160 words per minute for clear public speaking, about 150 words per minute
for conversational English, and faster broadcast-style delivery above that.
For reference, `2.8` Kazakh words/second equals `168` words/minute, so a segment
at `2.9` words/second is already treated as fast.
Short segments of `3.0` seconds or less are capped at `fast`, even when the
calculated density exceeds the `extreme` threshold; this avoids over-pressuring
brief lines into unnaturally rushed delivery.

| Category | Kazakh words/second | Prompt behavior |
| --- | ---: | --- |
| slow | `< 1.6` | Natural delivery without stretching or added pauses |
| normal | `1.6-2.4` | No timing note |
| brisk | `2.4-2.8` | Slightly brisk, compact delivery |
| fast | `2.8-3.3` | Fit target duration with brisk compact delivery |
| extreme | `> 3.3` and target duration `> 3.0s` | Fastest natural delivery, crisp syllables, no extra pauses |

For Chinese prompts, the same categories are based on Han characters per second
instead of whitespace-separated words. The Chinese thresholds use `4.3`
characters/second as the normal-to-brisk boundary, based on published
intelligibility/preference results for Chinese speech.

Reference points:

- [NCVS voice qualities](https://ncvs.org/tutorials/voice-qualities/) notes that
  the average U.S. English speech rate is about `150` words/minute.
- [Toastmasters vocal variety material](https://www.westsidetoastmasters.com/education/manuals/manual_cc_06_vocal_variety.pdf)
  recommends an effective speech-rate range of about `125-160` words/minute.
- [Chan and Lee, 2005](https://doi.org/10.1016/j.ergon.2004.09.001) reports high
  intelligibility and preference for Chinese speech around `4.3`
  characters/second.
