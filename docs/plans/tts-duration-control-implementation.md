# TTS duration control implementation plan

## Scope
Implement a practical segment-level duration control loop for Kazakh TTS generation so synthesized audio fits the source segment timeline more reliably.

This plan covers near-term engineering work only. It does not include voice annotation, multi-speaker synthesis, or advanced prosody transfer.

## Objective
Extend the current pipeline so that duration control is handled in two places:
1. translation prompt enforces rough source/target length similarity
2. TTS stage measures generated duration and applies bounded acoustic or timeline-safe handling when needed

## Success criteria
- Translation prompting explicitly requests rough source/target length similarity.
- Every synthesized segment has measured duration metadata.
- Each segment is classified against configured duration tolerances.
- Near-miss segments can go through bounded acoustic correction.
- Final composed audio avoids unsafe overlap with subsequent segments.
- Run artifacts and manifest expose what corrections were applied.
- Existing stub-mode and current real-provider flow continue to work.

## Out of scope
- New speech provider integration
- Voice annotation extraction
- Speaker-conditioned TTS
- Perfect prosody matching to source English
- Full end-to-end UI or productization work
- Post-translation rewrite loops in the TTS stage

## Target files

### Config
- `configs/default.yaml`
- `src/video_dub/config.py`

### Models / manifest
- `src/video_dub/models/segment.py`
- `src/video_dub/models/manifest.py`

### Services
- `src/video_dub/services/synthesis.py`
- `src/video_dub/services/audio_compose.py`
- `src/video_dub/services/subtitle.py` only if shared helpers are unexpectedly needed, otherwise no change

### Providers
- `src/video_dub/providers/gemini_tts_provider.py`
- `src/video_dub/providers/gemini_translate_provider.py`

### Pipeline / CLI
- `src/video_dub/pipeline.py`
- `src/video_dub/cli.py` only if new reporting flags or summaries are exposed

### Storage
- `src/video_dub/storage/artifacts.py`
- `src/video_dub/storage/run_layout.py` if new artifact directories are added

### Tests
- `tests/test_translate_provider.py`
- `tests/test_translation_service.py`
- `tests/test_tts_pipeline.py`
- `tests/test_pipeline.py`
- add targeted tests for duration-control logic

## Delivery strategy
Implement in three phases so useful behavior lands early and risk stays bounded.

---

## Phase 1: translation-side length control and duration measurement

### Goal
Reduce extreme mismatches before synthesis and make timing visible before adding DSP-based correction.

### Changes

#### 1. Update translation prompt contract
In the translation prompt files and provider flow, explicitly require rough source/target length similarity.

Prompt requirements:
- preserve meaning
- produce natural, speakable Kazakh
- keep source and target text lengths roughly similar
- avoid unnecessary expansion
- stay concise for short segments

This should be applied where translation prompting is defined so TTS receives better-shaped input by default.

#### 2. Add config section
In `configs/default.yaml`, add a new section for duration control.

Suggested fields:
- `tts_alignment.enabled: true`
- `tts_alignment.preferred_ratio_tolerance: 0.08`
- `tts_alignment.max_ratio_tolerance: 0.15`
- `tts_alignment.short_ratio: 0.85`
- `tts_alignment.severe_long_ratio: 1.35`
- `tts_alignment.pad_with_silence: true`
- `tts_alignment.allow_minor_overhang_seconds: 0.15`
- `tts_alignment.manual_review_on_failure: true`

In `src/video_dub/config.py`, expose typed config accessors for these values.

#### 3. Extend segment metadata
In `src/video_dub/models/segment.py`, add optional timing-control fields.

Suggested fields:
- `target_duration: float | None`
- `initial_tts_duration: float | None`
- `tts_duration: float | None` (reuse if already present for final duration)
- `duration_status: str | None`
- `correction_actions: list[str]`
- `time_stretch_ratio: float | None`
- `duration_error_seconds: float | None`

If `Segment` should remain focused on content only, put these in sidecar manifest structures instead. But near-term, keeping them on `Segment` is likely simplest.

#### 4. Measure synthesized duration immediately
In `src/video_dub/services/synthesis.py`:
- after each TTS segment WAV is written, measure actual WAV duration
- compute `target_duration = segment.end - segment.start`
- compute duration ratio and error
- classify into `preferred`, `acceptable`, `too_short`, `too_long`, `manual_review`
- persist metrics back to the segment object

Add small pure helpers for:
- WAV duration measurement
- duration ratio calculation
- status classification

These helpers should be unit-tested separately.

#### 5. Make composition timeline-safe
In `src/video_dub/services/audio_compose.py`:
- preserve current segment start anchoring
- detect whether a segment’s final audio would collide with the next segment start beyond allowance
- if a segment ends early and silence padding is enabled, pad silence at compose time rather than changing semantic timing
- if a segment is slightly long but does not exceed next-start allowance, allow it
- if a segment would exceed next-start allowance, mark it clearly for manual review and apply the safest minimal handling available

For Phase 1, do not trim voiced content automatically.
Only trim trailing silence if such a helper is straightforward and reliable.

#### 6. Persist debugging metadata
In `src/video_dub/models/manifest.py` and storage code:
- ensure duration control fields are serialized in transcript/manifest outputs
- optionally add run-level counters in the manifest, such as number of corrected or flagged segments

#### 7. Surface summary in pipeline logs
In `src/video_dub/pipeline.py`:
- after TTS stage, print a short summary:
  - total segments
  - preferred count
  - acceptable count
  - flagged count
  - manual-review count

This should be concise and operational, not verbose.

### Acceptance for Phase 1
- Translation prompt includes rough length-control guidance.
- TTS output works as before for happy path.
- Every segment has target and actual duration recorded.
- Segments outside tolerance are visible in artifacts/manifest.
- Final composition does not silently hide severe timing problems.

---

## Phase 2: bounded acoustic micro-adjustment

### Goal
Handle near-miss segments with small waveform adjustments after translation-side length control has already done the first pass.

### Changes

#### 1. Add optional time-stretch support
In `src/video_dub/services/synthesis.py` or a small audio helper module:
- add a utility that can stretch or compress WAV duration within a narrow bound
- keep this behind config

Suggested config:
- `tts_alignment.enable_time_stretch: true`
- `tts_alignment.max_time_stretch_ratio: 0.08`

#### 2. Apply only to near-miss cases
Use time-stretch only when:
- segment is outside tolerance after first-pass synthesis
- the remaining error is small enough to stay within configured ratio bounds
- the corrected result clearly improves fit

Do not use on severely mismatched segments.

#### 3. Record transformation metadata
Store:
- original duration before stretch
- applied stretch ratio
- final duration after stretch

### Acceptance for Phase 2
- Near-miss segments can be corrected without large quality degradation.
- Stretch is skipped automatically for cases that would require aggressive manipulation.
- Metadata makes it clear when waveform adjustment was used.

---

## Phase 3: prompt refinement and reporting

### Goal
Reduce mismatch rate further by refining translation prompting and make run quality easier to inspect.

### Changes

#### 1. Refine translation prompting
Adjust translation prompt guidance only if observed mismatch patterns show the default length-control instruction is insufficient.

Possible refinements:
- stronger conciseness wording for short segments
- clearer instruction to avoid unnecessary modifiers
- tighter emphasis on keeping source and target text lengths roughly similar

#### 2. Add manual-review reporting
In `src/video_dub/pipeline.py` or CLI summary output:
- surface which segments are marked `manual_review`
- include enough timing metadata to inspect them quickly

#### 3. Add aggregate timing metrics
Add run-level metrics such as:
- preferred count
- acceptable count
- corrected count
- manual-review count
- average absolute duration error

### Acceptance for Phase 3
- Translation prompt can vary by duration bucket if needed.
- Runs expose manual-review segments clearly.
- Aggregate timing metrics are available in logs or manifest.

---

## Detailed implementation notes

### Duration classification helper
Add a pure helper with roughly this behavior:
- compute `target_duration`
- if missing or non-positive, classify as `manual_review`
- compute `ratio = actual / target`
- return one of:
  - `preferred`
  - `acceptable`
  - `too_short`
  - `too_long`
  - `manual_review`

This helper should not perform I/O.

### Candidate selection policy
For this plan, candidate count remains simple:
- one primary TTS output in Phase 1
- one acoustically adjusted candidate in Phase 2 when allowed

Choose in this order:
1. preferred candidate
2. otherwise acceptable candidate
3. otherwise closest candidate that does not create unsafe overlap
4. otherwise closest candidate overall and mark `manual_review`

### Composition policy
At composition time, use the final chosen segment audio only.
Do not attempt cross-segment optimization in this implementation.
Each segment should remain locally decided and globally safe.

### Artifact policy
If storage cost is acceptable, add:
- `artifacts/tts_raw/` for first-pass synthesis
- `artifacts/tts/` for final accepted audio

If not, keep only final audio and metadata.

Recommendation:
- Phase 1 can skip `tts_raw/`
- Phase 2 can add it if debugging becomes hard

---

## Testing plan

### Unit tests
Add focused tests for pure helpers:
- duration measurement from WAV fixture
- ratio classification across threshold boundaries
- overlap decision logic

### Translation tests
Add or extend tests around translation prompting:
- prompt includes length-control instruction
- short-segment inputs keep the expected concise guidance
- existing translation behavior is not broken structurally

### Service tests
Add or extend tests around `src/video_dub/services/synthesis.py`:
- accepted segment without correction
- out-of-tolerance segment marked for manual review in Phase 1
- near-miss time-stretch path once Phase 2 is implemented
- candidate selection between raw and stretched result

### Pipeline tests
Extend `tests/test_tts_pipeline.py` and `tests/test_pipeline.py` for:
- manifest persistence of duration metadata
- summary reporting after TTS
- composition behavior with adjacent tight segments

### Suggested test ordering
1. pure helper tests
2. translation prompt tests
3. synthesis service tests with stubs/mocks
4. pipeline tests
5. optional real-provider smoke check later in Pixi

---

## Rollout checklist

### Phase 1 checklist
- [ ] Update translation prompt with rough length-control instructions
- [ ] Add `tts_alignment` config schema and defaults
- [ ] Expose config fields in `config.py`
- [ ] Add duration-control fields to segment or manifest model
- [ ] Implement WAV duration measurement helper
- [ ] Implement duration classification helper
- [ ] Store target/actual/error metrics on each segment
- [ ] Update manifest serialization
- [ ] Add TTS-stage summary logging
- [ ] Add tests for translation prompt, helper logic, and manifest output

### Phase 2 checklist
- [ ] Add bounded time-stretch helper
- [ ] Gate it behind config
- [ ] Apply only to near-miss cases
- [ ] Record stretch metadata
- [ ] Add tests for stretch path and guardrails

### Phase 3 checklist
- [ ] Refine translation prompt if observed mismatch patterns require it
- [ ] Add manual-review reporting
- [ ] Add aggregate timing metrics
- [ ] Add tests for reporting output if needed

---

## Risks and mitigations

### Risk: translation prompt length control is too weak
Mitigation:
- keep guidance explicit and simple
- inspect mismatch distribution after Phase 1
- refine prompt by duration bucket in Phase 3

### Risk: timing logic becomes hard to debug
Mitigation:
- persist explicit metadata per segment
- keep classification and selection in pure helpers with unit tests

### Risk: DSP stretch harms voice quality
Mitigation:
- allow only small ratio adjustments
- apply only after translation-side control
- skip entirely for large mismatches

### Risk: severe mismatch remains unsolved
Mitigation:
- mark `manual_review` rather than hiding the problem
- keep the pipeline running with the best safe candidate

---

## Recommended execution order
1. Update translation prompts for rough length control.
2. Implement Phase 1 fully.
3. Run tests and inspect manifest output on stub TTS.
4. Implement Phase 2 only for near-miss cases.
5. Validate behavior on a handful of short and long segments.
6. Implement Phase 3 only after mismatch patterns are observed.

## Definition of done
This work is done when:
- translation prompt includes rough source/target length control
- timing metadata exists for every TTS segment
- the pipeline applies bounded duration handling automatically
- the final mix avoids obvious unsafe overlap
- failures are surfaced explicitly instead of being hidden
- tests cover translation prompt behavior, threshold classification, correction flow, and manifest persistence
