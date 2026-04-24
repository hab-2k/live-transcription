# Normalized Streaming Transcription Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current NeMo pseudo-streaming path with a normalized, provider-agnostic streaming transcription architecture using `parakeet-unified-en-0.6b`, `silero-vad`, stable revisable transcript turns, and dev-only runtime controls.

**Architecture:** The backend will split transcription into four layers: provider adapters emit normalized provider updates, a transcript timeline assembler owns turn identity and revision semantics, a segmentation layer uses `silero-vad` plus text heuristics to finalize readable turns, and downstream coaching/UI consumers receive only normalized timeline events. The frontend will stop treating transcripts as append-only rows and instead render stable `turn_id` entries that update in place until finalization.

**Tech Stack:** FastAPI, Python 3.10 app env, Python 3.12 NeMo sidecar, `parakeet-unified-en-0.6b`, `silero-vad`, Electron, React, TypeScript, Vitest, Pytest.

---

## File Structure

### Backend contracts and config

- Modify: `backend/app/contracts/session.py`
  - Add nested dev-only transcription configuration models for provider selection, latency preset, segmentation policy, coaching window policy, and VAD settings.
- Modify: `backend/app/contracts/events.py`
  - Add normalized `transcript_turn` event shape with stable `turn_id` and `revision`.
- Modify: `backend/app/core/config.py`
  - Add backend defaults for provider, parakeet worker, `silero-vad`, segmentation, and runtime reconfiguration support.

### Backend transcription runtime

- Modify: `backend/app/services/transcription/base.py`
  - Replace the current file-buffer-oriented provider protocol with a normalized streaming provider boundary.
- Create: `backend/app/services/transcription/provider_updates.py`
  - Define `ProviderTranscriptUpdate`, capabilities, and provider health/status payloads.
- Create: `backend/app/services/transcription/timeline.py`
  - Own turn lifecycle, revisioning, ordering, and normalization into UI events.
- Create: `backend/app/services/transcription/segmentation.py`
  - Own source-aware and capture-mode-aware segmentation logic.
- Create: `backend/app/services/transcription/vad.py`
  - Wrap `silero-vad` behind a backend-owned interface.
- Create: `backend/app/services/transcription/runtime_controller.py`
  - Start, stop, and reconfigure the active provider pipeline for a session.
- Create: `backend/app/services/transcription/parakeet_unified_provider.py`
  - First production provider adapter using the unified model worker.
- Modify: `backend/app/services/transcription/registry.py`
  - Register the new provider and remove the hard-coded NeMo-only assumption.
- Modify: `backend/app/services/session_manager.py`
  - Replace append-only transcript handling with timeline assembly and configurable coaching windows.
- Modify: `backend/app/api/routes/session.py`
  - Accept advanced transcription config at session start and add a reconfiguration route.

### Backend worker and tooling

- Create: `backend/scripts/parakeet_unified_streaming_worker.py`
  - Long-lived sidecar worker for `parakeet-unified-en-0.6b`.
- Modify: `backend/scripts/benchmark_nemo_streaming.py`
  - Either rename or replace with a provider-agnostic benchmark harness that can benchmark the new provider.
- Modify: `backend/pyproject.toml`
  - Add `silero-vad` and any runtime dependencies needed in the app env.
- Modify: `.env.example`
  - Add defaults for the unified model and VAD/segmentation settings.
- Modify: `README.md`
  - Document the new provider, controls, and dev workflow.

### Backend tests and fakes

- Modify: `backend/tests/fakes/fake_provider.py`
  - Emit normalized provider updates rather than append-only transcript chunks.
- Create: `backend/tests/services/transcription/test_timeline.py`
  - Cover turn creation, revision, finalization, and ordering.
- Create: `backend/tests/services/transcription/test_segmentation.py`
  - Cover readable turn splitting across capture modes.
- Create: `backend/tests/services/transcription/test_vad.py`
  - Cover `silero-vad` wrapper behavior with deterministic fixtures or test doubles.
- Create: `backend/tests/services/transcription/test_parakeet_unified_provider.py`
  - Cover provider-to-update normalization and worker lifecycle.
- Modify: `backend/tests/services/session/test_session_runtime.py`
  - Cover coaching windows and transcript timeline behavior.
- Modify: `backend/tests/api/test_session_ws.py`
  - Cover new session config payloads and transcript turn event delivery.
- Modify: `backend/tests/services/transcription/test_registry.py`
  - Cover provider registration and selection.

### Frontend types, state, and UI

- Modify: `desktop/src/renderer/src/lib/types/session.ts`
  - Replace append-only transcript rows with normalized `transcript_turn` event types and dev config types.
- Modify: `desktop/src/renderer/src/lib/state/sessionReducer.ts`
  - Store turns by `turn_id`, update revisions in place, and track advanced settings state.
- Modify: `desktop/src/renderer/src/lib/api/client.ts`
  - Send advanced transcription config to the backend and parse the new event shapes.
- Modify: `desktop/src/renderer/src/App.tsx`
  - Wire setup/live advanced controls and reconfigure actions.
- Modify: `desktop/src/renderer/src/features/setup/SetupScreen.tsx`
  - Add dev-only advanced gear controls.
- Modify: `desktop/src/renderer/src/features/live/LiveScreen.tsx`
  - Add live advanced controls access beside the existing debug affordance.
- Modify: `desktop/src/renderer/src/features/debug/DebugDrawer.tsx`
  - Render provider diagnostics and live transcription settings.
- Modify: `desktop/src/renderer/src/features/live/TranscriptPanel.tsx`
  - Render revisable transcript turns instead of append-only rows.

### Frontend tests

- Modify: `desktop/src/renderer/src/test/session-reducer.test.ts`
  - Cover in-place turn updates and finalization.
- Modify: `desktop/src/renderer/src/test/session-client.test.ts`
  - Cover parsing of normalized transcript turn events and config payloads.
- Modify: `desktop/src/renderer/src/test/setup-screen.test.tsx`
  - Cover advanced setup controls and payload submission.
- Modify: `desktop/src/renderer/src/test/live-screen.test.tsx`
  - Cover live gear/debug controls.
- Modify: `desktop/src/renderer/src/test/transcript-panel.test.tsx`
  - Cover revisable rows and finalized display behavior.

## Task 1: Replace Session And Event Contracts

**Files:**
- Modify: `backend/app/contracts/session.py`
- Modify: `backend/app/contracts/events.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/contracts/test_events.py`
- Test: `backend/tests/api/test_session_ws.py`

- [ ] **Step 1: Write the failing backend contract tests**

```python
def test_transcript_turn_event_requires_turn_identity_and_revision() -> None:
    event = TranscriptTurnEvent(
        turn_id="turn-1",
        revision=2,
        event="updated",
        role="shared",
        source="microphone",
        text="thanks for calling",
        is_final=False,
        started_at="2026-04-24T08:00:00Z",
        ended_at="2026-04-24T08:00:01Z",
        confidence=0.92,
    )
    assert event.type == "transcript_turn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/contracts/test_events.py backend/tests/api/test_session_ws.py -v`

Expected: FAIL because `TranscriptTurnEvent` and the new session config fields do not exist yet.

- [ ] **Step 3: Implement the new session and event models**

```python
class TranscriptTurnEvent(BaseModel):
    type: Literal["transcript_turn"] = "transcript_turn"
    turn_id: str
    revision: int
    event: Literal["started", "updated", "finalized"]
    role: Literal["colleague", "customer", "shared", "unknown"]
    source: Literal["microphone", "blackhole", "mixed"]
    text: str
    is_final: bool
    started_at: str
    ended_at: str
    confidence: float
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/contracts/test_events.py backend/tests/api/test_session_ws.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/contracts/session.py backend/app/contracts/events.py backend/app/core/config.py backend/tests/contracts/test_events.py backend/tests/api/test_session_ws.py
git commit -m "feat: add normalized transcript turn contracts"
```

## Task 2: Introduce The Normalized Provider Boundary

**Files:**
- Modify: `backend/app/services/transcription/base.py`
- Create: `backend/app/services/transcription/provider_updates.py`
- Modify: `backend/tests/fakes/fake_provider.py`
- Modify: `backend/tests/services/transcription/test_provider_contract.py`
- Modify: `backend/tests/services/transcription/test_registry.py`

- [ ] **Step 1: Write the failing provider-boundary tests**

```python
async def test_fake_provider_emits_provider_updates() -> None:
    emitted = []
    provider = FakeProvider()

    await provider.start(emit_update=emitted.append)
    await provider.push_audio(source="microphone", pcm=[0.1, 0.2], sample_rate=16000)

    assert emitted[0].stream_id == "microphone"
    assert emitted[0].is_final is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_provider_contract.py backend/tests/services/transcription/test_registry.py -v`

Expected: FAIL because the provider protocol still uses `TranscriptChunk`.

- [ ] **Step 3: Implement the provider update types and protocol**

```python
@dataclass(slots=True)
class ProviderTranscriptUpdate:
    stream_id: str
    source: str
    text: str
    is_final: bool
    started_at: str
    ended_at: str
    confidence: float = 0.0
    sequence_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_provider_contract.py backend/tests/services/transcription/test_registry.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcription/base.py backend/app/services/transcription/provider_updates.py backend/tests/fakes/fake_provider.py backend/tests/services/transcription/test_provider_contract.py backend/tests/services/transcription/test_registry.py
git commit -m "feat: normalize transcription provider updates"
```

## Task 3: Build The Transcript Timeline Assembler

**Files:**
- Create: `backend/app/services/transcription/timeline.py`
- Modify: `backend/app/services/transcription/normalizer.py`
- Test: `backend/tests/services/transcription/test_timeline.py`
- Test: `backend/tests/services/transcription/test_normalizer.py`

- [ ] **Step 1: Write the failing timeline tests**

```python
def test_timeline_revises_open_turn_until_finalized() -> None:
    timeline = TranscriptTimelineAssembler()

    started = timeline.ingest(update_for("turn-a", "Thanks", is_final=False))
    updated = timeline.ingest(update_for("turn-a", "Thanks for calling", is_final=False))
    finalized = timeline.ingest(update_for("turn-a", "Thanks for calling", is_final=True))

    assert started.turn_id == updated.turn_id == finalized.turn_id
    assert [started.revision, updated.revision, finalized.revision] == [1, 2, 3]
    assert finalized.is_final is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_timeline.py backend/tests/services/transcription/test_normalizer.py -v`

Expected: FAIL because the assembler does not exist.

- [ ] **Step 3: Implement the timeline assembler**

```python
class TranscriptTimelineAssembler:
    def ingest(self, update: ProviderTranscriptUpdate, *, role: str) -> TranscriptTurnEvent:
        ...
```

Behavior:
- reuse the same `turn_id` for an open display turn
- increment `revision` on each update
- emit `started`, `updated`, and `finalized`
- never mutate a finalized turn

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_timeline.py backend/tests/services/transcription/test_normalizer.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcription/timeline.py backend/app/services/transcription/normalizer.py backend/tests/services/transcription/test_timeline.py backend/tests/services/transcription/test_normalizer.py
git commit -m "feat: add transcript timeline assembler"
```

## Task 4: Add Segmentation Policies And `silero-vad`

**Files:**
- Create: `backend/app/services/transcription/segmentation.py`
- Create: `backend/app/services/transcription/vad.py`
- Test: `backend/tests/services/transcription/test_segmentation.py`
- Test: `backend/tests/services/transcription/test_vad.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Write the failing segmentation and VAD tests**

```python
def test_mic_only_segmentation_breaks_long_running_text_after_silence() -> None:
    policy = SegmentationPolicy.for_capture_mode("mic_only")
    assert policy.should_finalize(current_text="long phrase", silence_ms=700, source="microphone") is True
```

```python
def test_silero_vad_wrapper_reports_speech_activity() -> None:
    vad = SileroVadService(model=FakeSileroModel([False, True]))
    assert vad.detect(frame_with_speech()).active is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_segmentation.py backend/tests/services/transcription/test_vad.py -v`

Expected: FAIL because the segmentation and VAD services do not exist.

- [ ] **Step 3: Implement `silero-vad` wrapper and segmentation rules**

```python
class SileroVadService(VadService):
    def detect(self, frame: np.ndarray, sample_rate: int) -> VadDecision:
        ...
```

Behavior:
- wrap `silero-vad` behind a small backend-owned interface
- support configurable sensitivity and hangover timing
- let segmentation consume normalized speech-activity decisions

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_segmentation.py backend/tests/services/transcription/test_vad.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcription/segmentation.py backend/app/services/transcription/vad.py backend/tests/services/transcription/test_segmentation.py backend/tests/services/transcription/test_vad.py backend/pyproject.toml
git commit -m "feat: add silero vad backed segmentation"
```

## Task 5: Implement The Parakeet Unified Worker

**Files:**
- Create: `backend/scripts/parakeet_unified_streaming_worker.py`
- Modify: `backend/tests/services/transcription/test_nemo_provider.py`
- Create: `backend/tests/services/transcription/test_parakeet_unified_provider.py`

- [ ] **Step 1: Write the failing worker-client test**

```python
async def test_worker_returns_provider_updates_from_decode_requests(tmp_path: Path) -> None:
    client = ParakeetUnifiedWorkerClient(...)
    await client.start()
    result = await client.decode(audio_path=tmp_path / "sample.wav", source="microphone")
    assert "text" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_parakeet_unified_provider.py -v`

Expected: FAIL because the worker and client do not exist.

- [ ] **Step 3: Implement the persistent worker**

```python
class BufferedParakeetUnifiedRuntime:
    def decode(self, *, audio_path: Path) -> dict[str, object]:
        ...
```

Behavior:
- load `parakeet-unified-en-0.6b` once
- use the model's supported buffered streaming path
- return normalized transcript text plus timing/confidence fields usable by the provider adapter

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_parakeet_unified_provider.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/parakeet_unified_streaming_worker.py backend/tests/services/transcription/test_parakeet_unified_provider.py
git commit -m "feat: add parakeet unified streaming worker"
```

## Task 6: Implement The `ParakeetUnifiedProvider`

**Files:**
- Create: `backend/app/services/transcription/parakeet_unified_provider.py`
- Modify: `backend/app/services/transcription/registry.py`
- Modify: `backend/tests/services/transcription/test_registry.py`
- Modify: `backend/tests/fakes/fake_provider.py`
- Test: `backend/tests/services/transcription/test_parakeet_unified_provider.py`

- [ ] **Step 1: Write the failing provider adapter test**

```python
async def test_provider_emits_partial_then_final_updates(tmp_path: Path) -> None:
    emitted = []
    provider = ParakeetUnifiedProvider(settings=settings, worker_client_factory=lambda **_: fake_worker)
    await provider.start(emit_update=emitted.append)
    await provider.push_audio(source="microphone", pcm=np.ones(3200), sample_rate=16000)
    assert emitted[-1].stream_id == "microphone"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_parakeet_unified_provider.py backend/tests/services/transcription/test_registry.py -v`

Expected: FAIL because the provider adapter and registry wiring do not exist.

- [ ] **Step 3: Implement the provider adapter and registry selection**

```python
def build_provider(provider_name: str, settings: Any) -> StreamingTranscriptionProvider:
    if provider_name == "parakeet_unified":
        return ParakeetUnifiedProvider(settings=settings)
```

Behavior:
- maintain source-local worker state
- emit normalized provider updates only
- stop treating append-only transcript text as the provider output contract

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/transcription/test_parakeet_unified_provider.py backend/tests/services/transcription/test_registry.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcription/parakeet_unified_provider.py backend/app/services/transcription/registry.py backend/tests/services/transcription/test_parakeet_unified_provider.py backend/tests/services/transcription/test_registry.py
git commit -m "feat: add parakeet unified provider adapter"
```

## Task 7: Rewire Session Runtime Around Timeline And Reconfiguration

**Files:**
- Create: `backend/app/services/transcription/runtime_controller.py`
- Modify: `backend/app/services/session_manager.py`
- Modify: `backend/app/api/routes/session.py`
- Modify: `backend/tests/services/session/test_session_runtime.py`
- Modify: `backend/tests/api/test_session_ws.py`

- [ ] **Step 1: Write the failing session-runtime tests**

```python
async def test_session_manager_broadcasts_turn_updates_and_finalized_turns() -> None:
    manager = build_manager_with_fake_provider_updates()
    session_id = await manager.start_session(config_with_advanced_controls())
    events = manager.list_events(session_id)
    assert any(event.type == "transcript_turn" and event.event == "updated" for event in events)
```

```python
def test_reconfigure_route_restarts_only_transcription_pipeline() -> None:
    response = client.post(f"/api/sessions/{session_id}/transcription-config", json=payload)
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/services/session/test_session_runtime.py backend/tests/api/test_session_ws.py -v`

Expected: FAIL because the manager and route still assume append-only transcript events and no reconfiguration route.

- [ ] **Step 3: Implement runtime controller and session wiring**

```python
class TranscriptionRuntimeController:
    async def reconfigure(self, *, session_id: str, config: TranscriptionConfig) -> None:
        ...
```

Behavior:
- capture stays running
- provider pipeline restarts for the session when transcription settings change
- finalized transcript turns are preserved
- a status event marks the reconfiguration boundary

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/pytest backend/tests/services/session/test_session_runtime.py backend/tests/api/test_session_ws.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcription/runtime_controller.py backend/app/services/session_manager.py backend/app/api/routes/session.py backend/tests/services/session/test_session_runtime.py backend/tests/api/test_session_ws.py
git commit -m "feat: rewire session runtime for turn based transcription"
```

## Task 8: Update Frontend Event Parsing And Transcript State

**Files:**
- Modify: `desktop/src/renderer/src/lib/types/session.ts`
- Modify: `desktop/src/renderer/src/lib/state/sessionReducer.ts`
- Modify: `desktop/src/renderer/src/lib/api/client.ts`
- Modify: `desktop/src/renderer/src/test/session-reducer.test.ts`
- Modify: `desktop/src/renderer/src/test/session-client.test.ts`

- [ ] **Step 1: Write the failing frontend state tests**

```ts
it("revises an existing transcript turn in place when revision increases", () => {
  const started = ingestTurn({ turn_id: "turn-1", revision: 1, event: "started", text: "Thanks", is_final: false });
  const updated = ingestTurn({ turn_id: "turn-1", revision: 2, event: "updated", text: "Thanks for calling", is_final: false });
  expect(updated.transcript[0].text).toBe("Thanks for calling");
  expect(updated.transcript).toHaveLength(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `corepack pnpm --dir desktop test -- run session-reducer session-client`

Expected: FAIL because the frontend still expects append-only `transcript` events.

- [ ] **Step 3: Implement turn-aware parsing and reducer logic**

```ts
export type TranscriptTurnEvent = {
  type: "transcript_turn";
  turn_id: string;
  revision: number;
  event: "started" | "updated" | "finalized";
  ...
};
```

Behavior:
- replace turns in place by `turn_id`
- ignore stale revisions
- keep finalized turns immutable

- [ ] **Step 4: Run tests to verify they pass**

Run: `corepack pnpm --dir desktop test -- run session-reducer session-client`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/src/renderer/src/lib/types/session.ts desktop/src/renderer/src/lib/state/sessionReducer.ts desktop/src/renderer/src/lib/api/client.ts desktop/src/renderer/src/test/session-reducer.test.ts desktop/src/renderer/src/test/session-client.test.ts
git commit -m "feat: support turn based transcript updates in frontend"
```

## Task 9: Add Dev-Only Advanced Transcription Controls

**Files:**
- Modify: `desktop/src/renderer/src/App.tsx`
- Modify: `desktop/src/renderer/src/features/setup/SetupScreen.tsx`
- Modify: `desktop/src/renderer/src/features/live/LiveScreen.tsx`
- Modify: `desktop/src/renderer/src/features/debug/DebugDrawer.tsx`
- Modify: `desktop/src/renderer/src/features/live/TranscriptPanel.tsx`
- Modify: `desktop/src/renderer/src/test/setup-screen.test.tsx`
- Modify: `desktop/src/renderer/src/test/live-screen.test.tsx`
- Modify: `desktop/src/renderer/src/test/transcript-panel.test.tsx`

- [ ] **Step 1: Write the failing UI tests**

```tsx
it("shows advanced transcription controls behind the setup gear button", async () => {
  render(<SetupScreen ... />);
  await user.click(screen.getByRole("button", { name: /advanced transcription/i }));
  expect(screen.getByLabelText(/vad sensitivity/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `corepack pnpm --dir desktop test -- run setup-screen live-screen transcript-panel`

Expected: FAIL because those controls do not exist yet.

- [ ] **Step 3: Implement setup/live advanced controls**

```tsx
<button aria-label="Advanced transcription" type="button">...</button>
```

Behavior:
- keep controls developer-only
- surface provider, chunking preset, segmentation, coaching window, and `silero-vad` settings
- allow live reconfiguration via explicit apply action

- [ ] **Step 4: Run tests to verify they pass**

Run: `corepack pnpm --dir desktop test -- run setup-screen live-screen transcript-panel`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add desktop/src/renderer/src/App.tsx desktop/src/renderer/src/features/setup/SetupScreen.tsx desktop/src/renderer/src/features/live/LiveScreen.tsx desktop/src/renderer/src/features/debug/DebugDrawer.tsx desktop/src/renderer/src/features/live/TranscriptPanel.tsx desktop/src/renderer/src/test/setup-screen.test.tsx desktop/src/renderer/src/test/live-screen.test.tsx desktop/src/renderer/src/test/transcript-panel.test.tsx
git commit -m "feat: add advanced transcription dev controls"
```

## Task 10: Finish Integration, Docs, And Verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `backend/scripts/benchmark_nemo_streaming.py`
- Modify: `backend/tests/integration/test_mode1_pipeline.py`
- Modify: `backend/tests/integration/test_mode2_pipeline.py`
- Create: `backend/tests/integration/test_transcription_reconfigure.py`

- [ ] **Step 1: Write the failing integration tests**

```python
async def test_mode2_pipeline_emits_revisable_turns_per_source() -> None:
    ...
    assert any(event["type"] == "transcript_turn" and event["source"] == "blackhole" for event in events)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/pytest backend/tests/integration/test_mode1_pipeline.py backend/tests/integration/test_mode2_pipeline.py backend/tests/integration/test_transcription_reconfigure.py -v`

Expected: FAIL until the full pipeline is wired.

- [ ] **Step 3: Implement remaining integration glue and docs**

```bash
# Update docs and defaults after the full pipeline is green
```

Work:
- document `parakeet-unified-en-0.6b`
- document `silero-vad`
- document dev-only runtime controls and reconfigure flow
- replace old benchmark naming that still implies NeMo TDT only

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
backend/.venv/bin/pytest backend/tests -v
corepack pnpm --dir desktop test -- run
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example backend/scripts/benchmark_nemo_streaming.py backend/tests/integration/test_mode1_pipeline.py backend/tests/integration/test_mode2_pipeline.py backend/tests/integration/test_transcription_reconfigure.py
git commit -m "feat: finish normalized streaming transcription refactor"
```

## Execution Notes

- Use @superpowers:test-driven-development on every task.
- Keep commits small and scoped to one task.
- Do not preserve the old append-only transcript event path once the new turn-based pipeline is wired.
- Prefer replacing the existing NeMo-specific assumptions outright instead of layering compatibility shims unless a failing integration test proves a shim is required.
- The repo currently has many untracked application files. Stage only the paths relevant to the current task commit.
