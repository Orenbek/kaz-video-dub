# Voice annotation proposal for future TTS support

## Status
Proposal only. Not planned for immediate implementation.

## Purpose
Capture a narrow set of transcription-time voice annotations that are most useful for downstream dubbing and TTS quality, without expanding scope into broad sentiment analytics or full sound-scene understanding.

## Recommendation
When this work is scheduled, focus only on annotations that directly help speech rendering:
- speaking rate
- pause structure
- relative energy
- utterance type
- basic emotion class
- non-speech events relevant to subtitle or dubbing decisions

Do not prioritize, for now:
- general intent labeling
- fine-grained sentiment analysis
- open-ended sound event taxonomy
- broad conversational analytics

## Why this scope
These labels have the clearest operational value for the dubbing pipeline:
- improve phrase planning before TTS
- help decide whether translated text should be compact or expressive
- influence punctuation or pause insertion
- provide future hooks for style-aware synthesis

They are also easier to map into deterministic downstream behavior than richer semantic labels.

## Proposed annotation schema direction
This should eventually live as structured fields on `Segment` or adjacent segment metadata, not embedded into transcript text.

Suggested fields:
- `speaking_rate`: `slow | normal | fast`
- `energy`: `low | medium | high`
- `utterance_type`: `statement | question | exclamation`
- `emotion`: `neutral | warm | serious | excited`
- `pause_before_seconds`: numeric
- `pause_after_seconds`: numeric
- `non_speech_events`: list of limited labels such as `laughter`, `sigh`, `music`, `applause`, `noise_overlap`

## How this would be used later
A later TTS planning stage could consume:
- source timing
- translated Kazakh text
- the annotation fields above

And produce:
- final TTS-ready text
- punctuation adjustments
- duration-control hints
- optional style instructions for the TTS provider

## Suggested rollout when revisited
1. Add schema only.
2. Populate pause structure and utterance type first.
3. Add energy and basic emotion.
4. Add a minimal non-speech event set.
5. Validate whether these signals actually improve TTS outcomes before expanding further.

## Risks
- annotation noise may reduce quality if labels are unstable
- too many classes will make downstream control logic brittle
- provider-dependent labels may be hard to keep consistent across models

## Decision
Keep this as a future proposal. Near-term engineering effort should stay focused on segment duration control for Kazakh TTS alignment.
