# TTS duration control implementation plan

## Scope
Implement a practical segment-level duration control loop for Kazakh TTS generation so synthesized audio fits the source segment timeline more reliably.

This plan covers near-term engineering work only. It does not include voice annotation, multi-speaker synthesis, or advanced prosody transfer.

## Objective
Extend the current pipeline so that duration control is handled in two places:
1. translation prompt enforces rough source/target length similarity
2. TTS stage applies collision-first evaluation, bounded acoustic correction, and timeline-safe handling

## Success criteria
- Translation prompting explicitly requests rough source/target length similarity.
- Every synthesized segment has measured duration metadata.
- Each segment records both duration quality and timeline safety information.
- Segments with timeline collision are handled with collision-first correction logic.
- Near-miss segments can go through bounded time-stretch when it clearly improves fit.
- Final composed audio avoids unsafe overlap with subsequent segments without trimming voiced content.
- Run artifacts and manifest expose what corrections were applied and which segments require manual review.
- Existing stub-mode and current real-provider flow continue to work.

## Out of scope
- New speech provider integration
- Voice annotation extraction
- Speaker-conditioned TTS
- Perfect prosody matching to source English
- Full end-to-end UI or productization work
- Post-translation rewrite loops in the TTS stage
- Voiced-content trimming

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
- add a separate repair entrypoint later if manual review workflow needs CLI support

### Storage
- `src/video_dub/storage/artifacts.py`
- `src/video_dub/storage/run_layout.py` if new artifact directories are added

### Tests
- `tests/test_translate_provider.py`
- `tests/test_translation_service.py`
- `tests/test_tts_pipeline.py`
- `tests/test_pipeline.py`
- `tests/test_duration_control.py`
- add targeted tests for repair artifact output later

## Delivery strategy
Implement in three phases so useful behavior lands early and risk stays bounded.

---

## Phase 1: translation-side length control and duration visibility

### Goal
Reduce extreme mismatches before synthesis and make timing / collision information visible before adding bounded DSP correction.

### Changes

#### 1. Update translation prompt contract
In the translation prompt files and provider flow, explicitly require rough source/target length similarity.

Prompt requirements:
- preserve meaning
- produce natural, speakable Kazakh
- keep source and target text lengths roughly similar
- avoid unnecessary expansion
- stay concise for short segments
- make wording suitable for dubbing

This should be applied where translation prompting is defined so TTS receives better-shaped input by default.

#### 2. Add config section
In `configs/default.yaml`, add a new section for duration control.

Suggested Phase 1 fields:
- `tts_alignment.enabled: true`
- `tts_alignment.preferred_ratio_tolerance: 0.08`
- `tts_alignment.max_ratio_tolerance: 0.15`
- `tts_alignment.pad_with_silence: true`
- `tts_alignment.allow_minor_overhang_seconds: 0.15`
- `tts_alignment.manual_review_on_failure: true`

In `src/video_dub/config.py`, expose typed config accessors for these values.

#### 3. Extend segment metadata
In `src/video_dub/models/segment.py`, add optional timing-control fields.

Suggested fields:
- `target_duration: float | None`
- `initial_tts_duration: float | None`
- `tts_duration: float | None`
- `duration_status: str | None`
- `duration_error_seconds: float | None`
- `correction_actions: list[str]`
- `time_stretch_ratio: float | None`
- `has_timeline_collision: bool | None`

If `Segment` should remain focused on content only, raw path / collision details can be stored in sidecar manifest structures instead. Near-term, keeping core timing metadata on `Segment` is simplest.

#### 4. Measure synthesized duration immediately
In `src/video_dub/services/synthesis.py`:
- after each TTS segment WAV is written, measure actual WAV duration
- compute `target_duration = segment.end - segment.start`
- compute duration ratio and error
- compute whether the segment collides with the next segment beyond allowance
- classify final visible state into `preferred`, `acceptable`, `too_short`, `too_long`, or `manual_review`
- persist metrics back to the segment object

Add small pure helpers for:
- WAV duration measurement
- duration ratio calculation
- duration-only classification
- max-safe-duration calculation
- collision detection

These helpers should be unit-tested separately.

#### 5. Make composition timeline-safe
In `src/video_dub/services/audio_compose.py`:
- preserve current segment start anchoring
- detect whether a segment’s final audio would collide with the next segment start beyond allowance
- if a segment ends early and silence padding is enabled, pad silence at compose time rather than changing semantic timing
- if a segment is slightly long but does not exceed next-start allowance, allow it
- if a segment exceeds next-start allowance, mark it clearly for manual review

For Phase 1:
- do not trim voiced content automatically
- real trailing-silence trim can remain deferred if helper quality is not yet sufficient

#### 6. Persist debugging metadata
In `src/video_dub/models/manifest.py` and storage code:
- ensure duration control fields are serialized in transcript/manifest outputs
- add run-level counters in the manifest, such as number of preferred / acceptable / manual-review segments

#### 7. Surface summary in pipeline logs
In `src/video_dub/pipeline.py`:
- after TTS stage, print a short summary:
  - total segments
  - preferred count
  - acceptable count
  - too_short count
  - too_long count
  - manual-review count

This should be concise and operational, not verbose.

### Acceptance for Phase 1
- Translation prompt includes rough length-control guidance.
- TTS output works as before for happy path.
- Every segment has target and actual duration recorded.
- Every segment has visible collision information or equivalent timeline-safe assessment.
- Segments outside tolerance are visible in artifacts/manifest.
- Final composition does not silently hide severe timing problems.

---

## Phase 2: collision-first bounded acoustic micro-adjustment

### Goal
Add bounded time-stretch only where it is clearly justified:
- to resolve timeline collision via limited compression
- or to improve `too_short` / `too_long` segments back into an acceptable range

### Changes

#### 1. Add optional time-stretch support
In `src/video_dub/services/synthesis.py` or a small audio helper module:
- add a utility that can stretch or compress WAV duration within a narrow bound
- keep this behind config

Suggested config:
- `tts_alignment.enable_time_stretch: true`
- `tts_alignment.max_time_stretch_ratio: 0.08`
- `tts_alignment.min_time_stretch_improvement_seconds: 0.05`

#### 2. Apply collision-first correction logic
Implement the agreed flow:
- first check whether raw output collides with the next segment
- if it collides, try bounded compression only if it can remove or materially reduce collision within `max_time_stretch_ratio`
- if it does not collide:
  - `preferred` stays as-is
  - `acceptable` stays as-is
  - `too_short` / `too_long` can try bounded stretch only if that can move them into acceptable range

Do not stretch merely to improve an already acceptable result.

#### 3. Record transformation metadata
Store:
- original duration before stretch
- applied stretch ratio
- final duration after stretch
- whether collision existed before stretch and after stretch

#### 4. Keep collision unresolved cases alive but visible
If a segment still collides after allowed stretch logic:
- do not fail the entire run by default
- keep the pipeline moving
- leave final exposure to compose-stage trailing-silence handling and, if still unresolved, `manual_review`

### Acceptance for Phase 2
- Collision cases can use bounded compression when that is enough to restore safety.
- `too_short` / `too_long` non-collision cases can use bounded stretch only when it clearly improves fit.
- `acceptable` non-collision cases are left untouched.
- Stretch is skipped automatically for cases that would require aggressive manipulation.
- Metadata makes it clear when waveform adjustment was used.

---

## Phase 3: repair workflow and reporting

### Goal
Make unresolved cases operationally manageable without violating the agreed boundary that TTS stage does not rewrite text.

### Changes

#### 1. Add manual-review artifact output
In `src/video_dub/pipeline.py` and storage code:
- output a repair artifact such as `manual_review_segments.json`
- include enough metadata to let a human fix only the problematic segments

Suggested fields per row:
- `segment_id`
- `start`
- `end`
- `text_en`
- `text_kk`
- `target_duration`
- `initial_tts_duration`
- `tts_duration`
- `duration_error_seconds`
- `has_timeline_collision`
- `duration_status`
- `correction_actions`
- `raw_tts_path`
- `tts_path`

#### 2. Add manual-review reporting
In `src/video_dub/pipeline.py` or CLI summary output:
- surface which segments are marked `manual_review`
- include enough timing metadata to inspect them quickly
- point users to the repair artifact path

#### 3. Prepare separate repair flow
Do not mix repair into the main TTS pipeline.
Instead, define a separate repair path that will later:
- read `manual_review_segments.json`
- let a human edit `text_kk` or supply repair instructions
- rerun only the specified segments
- replace repaired segment audio back into the run artifacts

#### 4. Add aggregate timing metrics
Add run-level metrics such as:
- preferred count
- acceptable count
- too_short count
- too_long count
- manual-review count
- average absolute duration error
- time-stretch applied count
- trailing-silence-trim count
- pad-silence count

### Acceptance for Phase 3
- Runs expose manual-review segments clearly.
- Repair input artifacts are available for the unresolved subset.
- Aggregate timing metrics are available in logs or manifest.
- The plan for targeted per-segment repair is explicit and decoupled from the main pipeline.

---

## Detailed implementation notes

### Duration classification helper
Add a pure helper with roughly this behavior:
- compute `target_duration`
- if missing or non-positive, classify as `manual_review`
- compute `ratio = actual / target`
- if collision is unresolved, do not treat the segment as final `preferred` or `acceptable`
- otherwise return one of:
  - `preferred`
  - `acceptable`
  - `too_short`
  - `too_long`
  - `manual_review`

This helper should not perform I/O.

### Collision-first policy
For this plan, decision order should be:
1. does the raw segment collide with the next segment?
2. if yes, can bounded compression eliminate or materially reduce collision?
3. if no collision, is the duration quality already preferred / acceptable?
4. if not, can bounded stretch move the segment into acceptable range?
5. if still unsafe at compose time, expose as `manual_review`

### Composition policy
At composition time, use the final chosen segment audio only.
Do not attempt cross-segment optimization in this implementation.
Each segment should remain locally decided and globally safe.

The only allowed compose-time manipulations are:
- pad silence
- allow minor overhang
- trim trailing silence if implemented robustly

### Artifact policy
If storage cost is acceptable, add:
- `artifacts/tts_raw/` for first-pass synthesis
- `artifacts/tts/` for final accepted audio
- `manual_review_segments.json` for unresolved segments

If not, the minimum should be:
- final audio
- transcript/manifest metadata
- manual review artifact

Recommendation:
- Phase 1 can keep only final audio plus metadata if needed
- Phase 2+ should strongly prefer preserving `tts_raw/` for debugging

---

## Testing plan

### Unit tests
Add focused tests for pure helpers:
- duration measurement from WAV fixture
- ratio classification across threshold boundaries
- max-safe-duration calculation
- collision detection
- time-stretch guardrail decisions

### Translation tests
Add or extend tests around translation prompting:
- prompt includes length-control instruction
- short-segment inputs keep the expected concise guidance
- existing translation behavior is not broken structurally

### Service tests
Add or extend tests around `src/video_dub/services/synthesis.py`:
- accepted segment without correction
- acceptable segment with collision enters correction path
- collision case uses bounded compression when possible
- acceptable non-collision segment is left untouched
- `too_short` / `too_long` segment stretches only when improvement is enough
- unresolved segment is preserved and surfaced for manual review

### Compose tests
Add or extend tests around `src/video_dub/services/audio_compose.py`:
- early-ending segments receive compose-time silence padding
- minor overhang is allowed within configured allowance
- unresolved collision becomes `manual_review`
- trailing-silence trim path once implemented robustly

### Pipeline tests
Extend `tests/test_tts_pipeline.py` and `tests/test_pipeline.py` for:
- manifest persistence of duration metadata
- summary reporting after TTS
- output of `manual_review_segments.json`
- composition behavior with adjacent tight segments

### Suggested test ordering
1. pure helper tests
2. translation prompt tests
3. synthesis service tests with stubs/mocks
4. compose tests
5. pipeline tests
6. optional real-provider smoke check later in Pixi

---

## Rollout checklist

### Phase 1 checklist
- [ ] Update translation prompt with rough length-control instructions
- [ ] Add `tts_alignment` config schema and defaults
- [ ] Expose config fields in `config.py`
- [ ] Add duration-control fields to segment or manifest model
- [ ] Implement WAV duration measurement helper
- [ ] Implement collision detection helper
- [ ] Implement duration-only classification helper
- [ ] Store target/actual/error/collision metrics on each segment
- [ ] Update manifest serialization
- [ ] Add TTS-stage summary logging
- [ ] Add tests for translation prompt, helper logic, and manifest output

### Phase 2 checklist
- [ ] Add bounded time-stretch helper
- [ ] Gate it behind config
- [ ] Implement collision-first correction logic
- [ ] Leave acceptable non-collision results untouched
- [ ] Record stretch metadata
- [ ] Add tests for stretch path and guardrails

### Phase 3 checklist
- [ ] Add `manual_review_segments.json` output
- [ ] Add manual-review reporting
- [ ] Define targeted repair flow contract
- [ ] Add aggregate timing metrics
- [ ] Add tests for reporting and repair artifact output

---

## Risks and mitigations

### Risk: translation prompt length control is too weak
Mitigation:
- keep guidance explicit and simple
- inspect mismatch distribution after Phase 1
- refine prompt wording if needed

### Risk: timing logic becomes hard to debug
Mitigation:
- persist explicit metadata per segment
- keep classification and collision logic in pure helpers with unit tests
- preserve raw and final audio artifacts where practical

### Risk: DSP stretch harms voice quality
Mitigation:
- allow only small ratio adjustments
- use it only for collision-first correction or clear duration improvement
- skip entirely for cases that would require aggressive manipulation

### Risk: severe mismatch remains unsolved
Mitigation:
- mark `manual_review` rather than hiding the problem
- keep the pipeline running
- emit a repair artifact for targeted follow-up

### Risk: repair workflow grows into implicit rewrite loop
Mitigation:
- keep repair as a separate script / workflow
- do not let main pipeline rewrite translation text after TTS measurement

---

## Recommended execution order
1. Update translation prompts for rough length control.
2. Finish Phase 1 visibility and collision metadata.
3. Run tests and inspect manifest output on stub TTS.
4. Implement collision-first bounded stretch in Phase 2.
5. Validate behavior on a handful of short, long, and tight-gap segments.
6. Implement manual-review artifact and repair-flow reporting in Phase 3.

## Definition of done
This work is done when:
- translation prompt includes rough source/target length control
- timing metadata exists for every TTS segment
- the pipeline evaluates collision before deciding correction
- bounded stretch is applied only in agreed scenarios
- the final mix avoids obvious unsafe overlap without trimming voiced content
- unresolved cases are surfaced explicitly and exported for targeted repair
- tests cover translation prompt behavior, collision logic, bounded stretch, manifest persistence, and manual-review artifact output
