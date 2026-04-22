# Kazakh TTS duration control design

## Status
Planned for near-term implementation.

## Problem
The current Gemini TTS API does not provide reliable duration targeting per segment. For dubbing, each synthesized Kazakh segment must fit the source segment time window closely enough that the final composed dub stays synchronized with the original video timeline.

A direct one-shot TTS call is therefore not sufficient. The pipeline needs an explicit duration control layer that measures generated audio, decides whether it is acceptable, and applies bounded correction strategies when it is not.

## Goals
- Keep each dubbed segment close to its source segment duration.
- Preserve naturalness before pursuing strict frame-perfect alignment.
- Avoid segment overlap in the final composed dub.
- Make the strategy deterministic and inspectable in run artifacts.
- Work with the current single-speaker Gemini TTS integration.

## Non-goals
- Perfect prosody transfer from source speech.
- Speaker style cloning.
- Full forced-alignment between synthesized Kazakh phonemes and source English speech.
- Multi-speaker timing optimization.
- Post-translation rewrite loops inside the TTS stage.

## Success criteria
For each segment, define:
- `target_duration = segment.end - segment.start`
- `actual_duration = synthesized wav duration`
- `duration_ratio = actual_duration / target_duration`
- `duration_error_seconds = actual_duration - target_duration`

Recommended acceptance bands:
- Preferred: within ±8%
- Acceptable: within ±15%
- Requires correction: outside ±15%

At composition time:
- No segment audio may start before its segment start time.
- No segment audio may overlap the next segment start by more than a small configured allowance.
- Early-finishing segments should be padded with silence rather than stretched to exact fill.

## Design principles
1. Text-side control should happen during translation, not after translation.
2. Acoustic post-processing is bounded and conservative.
3. Final timeline correctness matters more than exact per-segment equality.
4. Every correction step should be recorded in artifacts or manifest metadata.
5. Retry strategy should be limited so the pipeline remains predictable.

## Proposed pipeline stage
Insert a dedicated duration control loop inside the TTS stage, while making translation responsible for rough text-length control.

Current logical flow:
- translation
- TTS generation
- audio compose

Proposed flow:
- translation with length-control prompt
- TTS generation
- duration evaluation
- bounded acoustic correction if needed
- audio compose

## Role of translation
Length control belongs in translation prompting.

The translation prompt should ask for:
- preserved meaning
- natural, speakable Kazakh
- source and target text lengths that stay roughly similar
- concise phrasing for short source segments
- no unnecessary expansion beyond what dubbing can tolerate

This does not guarantee final audio duration, but it should reduce the number of extreme mismatches before TTS begins.

## Segment-level algorithm

### Inputs
For each segment:
- source timing: `start`, `end`
- translated Kazakh text: `text_kk`
- optional punctuation/features already present in text
- configurable thresholds

### Outputs
For each segment:
- final `tts_path`
- final `tts_duration`
- control metadata describing how the segment reached acceptance

### Step 1: compute target window
For segment `s`:
- `target_duration = s.end - s.start`

### Step 2: first-pass synthesis
Generate TTS once using the translated text as-is.
Measure output WAV duration immediately.

If within preferred or acceptable tolerance, accept it.

### Step 3: classify mismatch
If outside tolerance, classify as:
- `too_short`
- `slightly_too_long`
- `severely_too_long`

Recommended initial thresholds:
- `too_short`: actual < 0.85 * target
- `slightly_too_long`: 1.15 * target < actual <= 1.35 * target
- `severely_too_long`: actual > 1.35 * target

### Step 4: correction order
Apply correction strategies in this order.

#### 4.1 Apply bounded time-stretch
If the generated audio is close enough to the target, apply mild time-stretch.

Recommended stretch bounds:
- speed-up lower bound: 0.92x original duration equivalent
- slow-down upper bound: 1.08x original duration equivalent

Equivalent interpretation:
- only allow roughly ±8% waveform duration correction
- never use aggressive stretch that noticeably damages voice quality

This stage is suitable only for near-miss cases. If a segment lies far outside the target, the system should accept imperfect fit or mark it for manual review instead of trying to repair it with large DSP changes.

#### 4.2 Timeline-safe padding or trimming
Final handling before composition:
- if accepted audio ends early, append silence so the composed dub preserves spacing
- if audio is only slightly too long but still does not collide with the next segment, keep it
- if audio would collide with the next segment, trim only trailing silence first; do not trim voiced content unless explicitly configured

## Why this ordering
This ordering protects naturalness:
- translation prompt controls lexical density early, where it belongs
- mild stretch can correct a small residual mismatch
- silence padding is harmless when a segment ends early
- hard trimming or large stretch is avoided because it degrades quality fastest

## Configuration proposal
Add a `tts_alignment` section in `configs/default.yaml`.

Example fields:
- `enabled: true`
- `preferred_ratio_tolerance: 0.08`
- `max_ratio_tolerance: 0.15`
- `severe_long_ratio: 1.35`
- `short_ratio: 0.85`
- `enable_time_stretch: true`
- `max_time_stretch_ratio: 0.08`
- `pad_with_silence: true`
- `allow_minor_overhang_seconds: 0.15`
- `manual_review_on_failure: true`

These names are illustrative; exact naming can be refined during implementation.

## Metadata to persist
Persist per-segment duration control metadata in manifest or transcript artifacts.

Recommended fields:
- `target_duration`
- `initial_tts_duration`
- `final_tts_duration`
- `duration_status` (`preferred`, `acceptable`, `corrected`, `manual_review`)
- `correction_actions` (ordered list such as `time_stretch`, `pad_silence`)
- `time_stretch_ratio`

This is important for debugging because timing problems are difficult to reason about after the final mix has been produced.

## Artifact proposal
Store intermediate corrected segment audio under the run directory so each segment can be inspected.

Suggested pattern:
- `runs/<job-id>/artifacts/tts_raw/*.wav`
- `runs/<job-id>/artifacts/tts/*.wav`

Where:
- `tts_raw` stores the first-pass synthesis result
- `tts` stores the accepted final segment audio used for composition

If keeping both is too heavy, the minimum should be manifest metadata plus final audio.

## Failure policy
If a segment cannot be brought within acceptable tolerance after bounded correction:
- keep the best candidate that does not create unsafe overlap if possible
- mark the segment as `manual_review`
- continue the pipeline instead of failing the entire run by default

Hard failure should be reserved for cases where:
- no audio was generated
- audio is corrupted or unreadable
- timeline collision is severe enough that composition would clearly break

## Interaction with translation
Translation should expose a dubbing-oriented mode:
- preserve meaning
- prefer concise, speakable Kazakh
- keep source and target text lengths roughly similar
- respect rough duration budget implied by segment timing

The TTS stage should rely on this translation behavior rather than introducing a separate post-translation rewrite loop.

## Suggested implementation phases

### Phase 1
- Update translation prompting to request rough source/target length matching.
- Measure every synthesized segment duration.
- Accept within tolerance.
- Pad early endings with silence.
- Mark overlong segments in metadata.
- Avoid overlap in composition.

This gives visibility quickly with low complexity.

### Phase 2
- Add bounded time-stretch for near-miss cases.
- Persist correction metadata.
- Add manual-review reporting in CLI output.

### Phase 3
- Refine translation prompt if observed mismatch patterns show the current length-control guidance is insufficient.
- Add aggregate run metrics for timing fitness.

## Open questions
- Should segment duration tolerance depend on neighboring gap size rather than only local ratio?
- Should very short segments be merged before TTS instead of individually controlled?
- Should punctuation in `text_kk` be normalized specifically for dubbing rhythm?
- Should translation prompting remain one global rule or split into multiple modes later?

## Recommendation
Implement Phase 1 first, then Phase 2. That gives a practical path to improved synchronization without overcommitting to a complex prosody system too early.
