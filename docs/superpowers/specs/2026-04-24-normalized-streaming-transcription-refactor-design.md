# Normalized Streaming Transcription Refactor Design

## Summary

Refactor the backend transcription architecture so that:

- ASR providers are fully replaceable behind a normalized backend contract
- the UI consumes only stable, provider-agnostic transcript timeline events
- transcript rows can be revised in place via stable `turn_id` semantics
- display segmentation is readable and user-friendly instead of append-only text growth
- lightweight VAD informs silence-sensitive segmentation and finalization
- advanced transcription controls are exposed through dev-only gear/debug surfaces in setup and live views

The first implementation target is `nvidia/parakeet-unified-en-0.6b`, using its official buffered streaming path rather than the current pseudo-streaming full-history re-decode architecture.

## Problem Statement

The current NeMo integration is not fit for purpose:

- the provider repeatedly re-decodes growing source history instead of maintaining a proper streaming session
- the backend contract conflates provider hypotheses, display rows, and coaching inputs
- transcript events are append-only and have no stable identity, so the frontend cannot revise a turn in place
- segmentation is accidental rather than product-driven
- provider-specific behavior leaks too far into orchestration decisions

This makes the current implementation both slow and structurally hard to replace.

## Goals

- Replace the current NeMo-side architecture with a layered streaming transcription pipeline.
- Make the provider boundary strongly normalized so future ASR engines can be swapped in without frontend changes.
- Introduce stable transcript turn identities and revisions for in-place UI updates.
- Keep display turns readable with sensible segmentation rules instead of a wall of text.
- Support different default segmentation behavior for `mic_only` and `mic_plus_blackhole`.
- Use lightweight VAD as a segmentation and finalization signal.
- Keep coaching and summary consumers independent from provider-native output.
- Expose dev-only transcription controls in setup and live debug surfaces.

## Non-Goals

- No commitment to a cache-aware streaming model in this refactor.
- No end-user exposure of advanced transcription settings.
- No requirement that every runtime parameter be hot-swappable without a provider restart.
- No coupling of the UI to provider-native chunks, token streams, or model-specific metadata.

## Confirmed Product Decisions

- The backend owns transcript normalization and display-friendly segmentation.
- The provider contract must be very normalized and provider-agnostic.
- The UI must receive stable `turn_id`-based transcript updates that can be revised in place until finalized.
- Display segmentation and coaching evaluation windows are configurable concerns and are not identical by definition.
- Segmentation defaults may differ by capture mode.
- Lightweight VAD should be available as a backend segmentation signal.
- Advanced transcription controls are dev-only and exposed through a gear/debug affordance.
- The same advanced controls should be reachable from setup and from the live screen.
- Runtime changes should reconfigure or restart only the active transcription pipeline for the session, not the whole backend process.

## Architecture

### Layer 1: Audio Capture

The existing capture layer continues to produce normalized `AudioFrame` values per source:

- `microphone`
- `blackhole`

This layer remains responsible only for device input and low-level source labeling.

### Layer 2: Streaming ASR Provider Adapter

Each ASR implementation lives behind a provider adapter that:

- starts and stops provider-specific streaming state
- accepts source-tagged audio frames
- emits normalized provider transcript updates
- reports provider health and configuration metadata for debug use

This layer may depend on NeMo, cloud APIs, or future local engines, but it must not emit UI events directly.

### Layer 3: Transcript Timeline Orchestrator

This new backend layer is the core of the refactor. It owns:

- stable `turn_id` allocation
- per-turn revision numbers
- open-turn tracking by source and display segment
- readable display segmentation
- turn finalization
- source-to-role mapping
- capture-mode-aware behavior
- translation from provider updates into normalized UI transcript events

This layer is the product boundary. It decides what the user sees and when.

### Layer 4: Downstream Consumers

Coaching, summaries, rule evaluation, and WebSocket broadcasting consume only normalized transcript timeline events and session status events.

They do not consume:

- raw provider hypotheses
- provider-native chunk windows
- provider-native timestamps that have not been normalized
- model-specific metadata

## Backend Contracts

### Provider Boundary

Providers normalize native output into a small internal shape, tentatively named `ProviderTranscriptUpdate`.

Required fields:

- `stream_id`
- `source`
- `text`
- `is_final`
- `started_at`
- `ended_at`

Optional fields:

- `confidence`
- `sequence_number`
- `metadata`

Contract semantics:

- `stream_id` identifies one provider-side stream for a given session and source path
- updates are progressive views of the provider's current hypothesis for that stream
- `metadata` is for diagnostics only and cannot be required by downstream product logic
- providers may emit multiple partial updates before a final update

This contract is intentionally narrow. It expresses provider belief, not UI state.

### UI Boundary

The backend emits normalized transcript timeline events. The UI consumes only these normalized events.

Recommended shape:

- `type: "transcript_turn"`
- `turn_id`
- `revision`
- `event`
- `role`
- `source`
- `text`
- `is_final`
- `started_at`
- `ended_at`
- `confidence`

Where `event` is one of:

- `started`
- `updated`
- `finalized`

Contract semantics:

- `turn_id` is stable for the life of one display turn
- `revision` increments each time an open turn changes
- the UI replaces an existing turn in place when it receives the same `turn_id` with a higher `revision`
- once `is_final` is `true`, that turn becomes immutable
- finalized turns are never rewritten under the same `turn_id`

The backend may continue to emit other normalized session events such as:

- `session_status`
- `voice_activity`
- `coaching_nudge`
- `rule_flag`

But transcript display must move to the new turn-based contract.

## Display Segmentation Model

The refactor must explicitly separate:

- provider hypotheses
- display turns
- coaching evaluation units

These are related but not the same thing.

### Display Turn Goals

Display turns should be:

- readable at a glance
- stable enough to avoid flicker
- segmented in a way that feels conversational
- appropriate to the capture mode

### Default Segmentation Behavior

For `mic_plus_blackhole`:

- segment independently by source
- preserve lane readability for colleague versus customer audio
- break on source changes, provider finalization, silence, major punctuation, and length thresholds

For `mic_only`:

- segment for readability rather than speaker identity
- break on silence, punctuation, stabilization windows, and length thresholds
- avoid long unbroken paragraphs in the transcript surface

### Segmentation Signals

The segmentation policy may use:

- provider final updates
- punctuation
- text length thresholds
- silence windows from VAD
- source boundaries
- configurable stabilization delays

The orchestrator, not the provider, decides when a provider update should:

- revise the current display turn
- finalize the current display turn
- start a new display turn

## Lightweight VAD

The backend should include a lightweight VAD service used for segmentation hints and finalization decisions.

Initial expectations:

- low overhead
- local execution
- per-source activity state
- configurable sensitivity and hangover timing

The first implementation does not need a heavy ML VAD. It may extend the existing RMS/activity logic into a more explicit silence detector with debounce and hold timings, provided the contract stays backend-owned and replaceable.

VAD is a segmentation input, not a provider requirement.

## Coaching Evaluation Units

Coaching and rules should not be hard-coded to consume every partial transcript update.

The backend should support configurable coaching window policies such as:

- finalized display turns only
- fixed recent text window
- source-specific finalized turns
- capture-mode-aware defaults

Default behavior remains backend-managed, with developer overrides available through advanced controls.

## Runtime Controls

Advanced transcription controls are developer-only.

They should be exposed in:

- setup screen advanced gear section
- live screen debug or gear surface

The controls may include:

- ASR provider selection
- provider/model preset
- latency or chunking preset
- segmentation policy
- coaching evaluation policy
- VAD sensitivity
- silence hold timings
- capture-mode-specific overrides

### Reconfiguration Behavior

At setup time:

- selected values become part of the session configuration
- the session starts with those settings applied

During a live session:

- changing a transcription-affecting setting should require an explicit apply action
- apply should restart only the transcription pipeline for that session
- the backend emits a normalized status event indicating transcription was reconfigured
- existing finalized turns remain preserved
- the backend may insert a transcript boundary or session marker at the reconfiguration point

The backend process itself should not be restarted just to apply a session-level transcription change.

## Frontend Changes

The frontend transcript state must move from append-only rows to turn-aware state.

Required behavior:

- store transcript turns by stable `turn_id`
- replace turns in place when a newer `revision` arrives
- preserve ordering for display
- treat finalized turns as immutable
- keep transcript rendering independent from provider-specific logic

The setup screen should gain a dev-only advanced gear section.

The live screen should extend the existing debug or gear pattern to surface the same transcription controls plus current provider diagnostics.

## Backend Components

The refactor should introduce explicit backend modules with clear responsibility boundaries.

Suggested components:

- `StreamingTranscriptionProvider` protocol
- `ParakeetUnifiedProvider`
- `TranscriptTimelineAssembler`
- `SegmentationPolicy`
- `VadService`
- `CoachingWindowPolicy`
- `TranscriptionRuntimeController`

`SessionManager` should become thinner and primarily coordinate lifecycle and event routing.

## Migration Strategy

### Phase 1

- replace the current provider protocol with the normalized streaming provider boundary
- add the transcript timeline assembler and new transcript turn events
- update backend contract tests

### Phase 2

- implement `ParakeetUnifiedProvider` using the unified model's official buffered streaming path
- remove the current full-history WAV re-decode logic

### Phase 3

- update frontend reducer and transcript rendering to support `turn_id` and `revision`
- add setup and live advanced controls

### Phase 4

- wire coaching to configurable evaluation units
- add integration coverage across capture modes and runtime reconfiguration

## Testing Strategy

Backend tests:

- provider normalization tests
- transcript timeline assembler tests
- segmentation policy tests for both capture modes
- VAD-informed finalization tests
- session reconfiguration tests

Frontend tests:

- reducer tests for in-place turn updates
- transcript panel tests for partial-to-final turn transitions
- setup advanced controls tests
- live debug or gear control tests

Integration tests:

- `mic_only` streaming session with revisable turns
- `mic_plus_blackhole` dual-source streaming session
- runtime reconfiguration of transcription settings
- coaching evaluation policy behavior against finalized and non-finalized transcript flow

## Risks And Tradeoffs

- `parakeet-unified-en-0.6b` still uses buffered streaming rather than cache-aware streaming, so this refactor fixes architecture and contract quality first, not the entire latency ceiling
- runtime reconfiguration adds lifecycle complexity and requires explicit session-status feedback
- segmentation quality will require tuning, especially for `mic_only`
- a normalized provider contract must stay minimal enough to support future engines without becoming lowest-common-denominator in a bad way

## Success Criteria

- swapping the ASR provider no longer requires frontend changes
- transcript rows update in place using stable `turn_id` and `revision`
- finalized transcript turns remain readable and sensibly segmented
- `mic_only` and `mic_plus_blackhole` use appropriate default segmentation behavior
- coaching and summaries consume normalized transcript timeline data rather than provider-native output
- developers can compare transcription parameter changes from setup or live debug controls without restarting the entire backend
