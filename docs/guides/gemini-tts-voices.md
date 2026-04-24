# Gemini TTS voices

Gemini TTS uses a prebuilt `voice_name` inside `speech_config.voice_config`.
Configure it with `tts.gemini_voice_name`:

```yaml
tts:
  use_stub: false
  model_name: gemini-3.1-flash-tts-preview
  gemini_voice_name: Kore
```

`tts.voice` is still supported as a legacy fallback, but Gemini runs should prefer
`tts.gemini_voice_name` so the config matches the provider API field.

You can compare these speaker voices in Google AI Studio:
https://aistudio.google.com/generate-speech

## Available voices

| Voice name | Style |
| --- | --- |
| Zephyr | Bright / 明亮 |
| Puck | Upbeat / 欢快 |
| Charon | Informative / 信息丰富 |
| Kore | Firm / 坚定 |
| Fenrir | Excitable / 兴奋 |
| Leda | Youthful / 青春 |
| Orus | Firm / 坚定 |
| Aoede | Breezy / 轻快 |
| Callirrhoe | Easy-going / 随和 |
| Autonoe | Bright / 明亮 |
| Enceladus | Breathy / 气声 |
| Iapetus | Clear / 清晰 |
| Umbriel | Easy-going / 轻松自在 |
| Algieba | Smooth / 平滑 |
| Despina | Smooth / 平滑 |
| Erinome | Clear / 清晰 |
| Algenib | Gravelly / 沙哑 |
| Rasalgethi | Informative / 信息丰富 |
| Laomedeia | Upbeat / 欢快 |
| Achernar | Soft / 柔和 |
| Alnilam | Firm / 坚定 |
| Schedar | Even / 平稳 |
| Gacrux | Mature / 成熟 |
| Pulcherrima | Forward / 直率 |
| Achird | Friendly / 友好 |
| Zubenelgenubi | Casual / 随意 |
| Vindemiatrix | Gentle / 温柔 |
| Sadachbia | Lively / 活泼 |
| Sadaltager | Knowledgeable / 知识渊博 |
| Sulafat | Warm / 温暖 |

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
  gemini_voice_name: Alnilam
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
