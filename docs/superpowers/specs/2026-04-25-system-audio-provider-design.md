# System Audio Provider Rewrite Design

## Problem

The current macOS system audio path is built around a Core Audio tap helper binary and a Python wrapper that exposes process-specific details directly to the rest of the app. That implementation is proving too unwieldy to operate and evolve. We need to replace the macOS backend with ScreenCaptureKit while also introducing a provider boundary strong enough to support a future Windows implementation without another contract rewrite.

## Goals

- Replace the current Core Audio tap implementation with a ScreenCaptureKit-backed implementation on macOS.
- Define a stable system audio provider contract that hides platform-specific details from the rest of the app.
- Move permission and readiness checks into the provider layer so the setup flow can surface clear status before session start.
- Remove `system_audio_pid` from the public session contract in favor of an opaque provider-backed target selection.
- Keep the rest of the transcription pipeline working with the existing `AudioFrame` shape.
- Make the future Windows port an implementation concern behind the same contract.

## Non-Goals

- Implement Windows system audio capture in this rewrite.
- Add multi-target capture in v1.
- Redesign mic capture; microphone capture remains handled by `SoundDeviceCaptureService`.
- Push speaker-role logic into the provider layer.

## Decision Summary

We will introduce a provider-first system audio architecture.

- The app will talk to a `SystemAudioProvider` contract instead of a macOS-specific service.
- The macOS implementation will use ScreenCaptureKit behind that contract.
- The backend and frontend will work with provider status and opaque target identifiers rather than raw process IDs.
- Session and transcription logic will continue to receive `AudioFrame(source="system")`, and the semantic mapping of `system -> customer` will live outside the provider.

## Architecture

Mic capture and system audio capture remain separate concerns.

- `SoundDeviceCaptureService` continues to manage microphone capture only.
- A new `SystemAudioProvider` boundary owns:
  - provider readiness and permission state
  - target discovery
  - system audio start and stop
  - normalization of provider-specific failures
- Session startup composes both paths:
  - `mic_only`: start microphone only
  - `mic_plus_system`: start microphone and selected system audio provider target

The transcription pipeline remains unchanged at the frame boundary:

- microphone capture emits `AudioFrame(source="microphone")`
- system audio provider emits `AudioFrame(source="system")`

This preserves the current segmentation and downstream frame flow while giving us a platform-neutral seam for system audio.

## Provider Contract

The contract must hide platform-specific identifiers, especially `pid`, from the public app contract.

### Provider interface

```python
class SystemAudioProvider(Protocol):
    def get_status(self) -> SystemAudioProviderStatus: ...
    def list_targets(self) -> list[SystemAudioTarget]: ...
    async def start(
        self,
        selection: SystemAudioSelection,
        sample_rate: int,
        on_audio: AudioSink,
    ) -> None: ...
    async def stop(self) -> None: ...
```

### Shared types

`SystemAudioProviderStatus`

- `state`: `available | permission_required | unsupported | error`
- `provider`: `screen_capture_kit | wasapi_process_loopback | none`
- `message`: short user-safe explanation for setup UI and logs

`SystemAudioTarget`

- `id`: opaque provider-defined identifier
- `name`: display name
- `kind`: `application` for v1
- `icon_hint`: optional string for future UI improvements
- `metadata`: provider-owned details such as `pid`, `bundle_id`, or executable path

`SystemAudioSelection`

- `provider`: provider identifier
- `target_id`: opaque identifier returned by `list_targets()`

### Contract rules

- `list_targets()` may return an empty list while still reporting `available`.
- `get_status()` must be cheap enough to call during setup flow refresh.
- `start()` must validate that the requested selection belongs to the active provider.
- `stop()` must be idempotent.
- Provider implementations may use private native details internally, but those details must not leak into `SessionConfig` or frontend state contracts.

## Backend API Contract

The setup flow should work from a single system-audio capability endpoint instead of separate platform-specific assumptions.

### New backend response shape

`GET /api/system-audio`

Returns:

- provider status
- provider id
- user-safe message
- available targets

Example shape:

```json
{
  "provider": "screen_capture_kit",
  "state": "available",
  "message": "Ready to capture system audio.",
  "targets": [
    {
      "id": "screen_capture_kit:com.microsoft.teams2:1234",
      "name": "Microsoft Teams",
      "kind": "application",
      "icon_hint": null
    }
  ]
}
```

### Session start contract

Replace:

- `system_audio_pid: int | None`

With:

- `system_audio_selection: { provider: str, target_id: str } | null`

This keeps the session API stable even if the provider changes how it identifies targets internally.

## macOS Implementation

The new macOS implementation will be `ScreenCaptureKitSystemAudioProvider`.

### Responsibilities

- query ScreenCaptureKit permission/readiness state
- enumerate capture targets for the setup picker
- start audio capture for the selected target
- resample or normalize output to the backend's expected format
- emit raw PCM as `AudioFrame(source="system")`
- shut down native resources cleanly on stop or failure

### Native boundary

We will keep the native-helper pattern, but the helper will become ScreenCaptureKit-specific instead of Core Audio tap-specific.

The Python backend remains responsible for:

- spawning the helper
- reading stdout PCM
- logging stderr
- converting helper failures into normalized provider errors

This keeps platform-specific capture code isolated and lets us rewrite the helper again later without changing session orchestration.

## Session And Transcription Semantics

The provider layer is responsible only for capture mechanics.

- it emits `AudioFrame(source="system")`
- it does not assign roles like `customer` or `colleague`

The transcription/session layer owns the semantic mapping:

- `microphone -> colleague`
- `system -> customer`

This rule is stable across platforms and should be treated as product logic, not provider logic.

## Failure Model

System audio should behave like a capability with explicit state, not a hidden start-time gamble.

### Setup-time states

- `available`: provider is usable
- `permission_required`: user must grant permission before capture can start
- `unsupported`: current platform or OS version cannot provide system audio
- `error`: provider encountered an unexpected failure while checking readiness

### Start-time failures

Normalize native/provider-specific failures into stable backend errors such as:

- invalid provider selection
- target unavailable
- permission required
- provider startup failure

### Mid-session failures

If system audio fails mid-session:

- log the provider-specific reason
- emit a normalized session error or status event
- stop system-audio capture cleanly
- avoid leaking native resources or orphaned subprocesses

Mic capture should remain independently stoppable and debuggable; system audio failure handling should not depend on provider-specific knowledge outside the provider boundary.

## Migration

This rewrite replaces the Core Audio tap path as the active macOS implementation.

Migration steps at a design level:

1. Introduce shared provider types and interface.
2. Update API and session contracts to use provider-backed selection.
3. Implement the ScreenCaptureKit-backed provider.
4. Update setup flow to consume provider status plus target list.
5. Remove direct `system_audio_pid` usage from backend and frontend.
6. Retire the Core Audio tap-specific implementation once the new provider is wired and verified.

## Testing Strategy

We should test at three levels.

### Contract tests

- provider status mapping
- target enumeration shape
- selection validation
- lifecycle semantics for `start()` and `stop()`
- normalized error mapping

### Backend integration tests

- `/api/system-audio` returns provider state and targets
- session start accepts provider-backed selection
- session start rejects invalid or stale selections
- system audio frames still feed the existing session pipeline correctly

### Native contract tests

- ScreenCaptureKit helper can report readiness
- helper can enumerate targets
- helper can start capture for a selected target
- helper exits cleanly on shutdown

## Future Windows Compatibility

The provider contract is intentionally designed so a Windows implementation can slot in later:

- provider id changes to `wasapi_process_loopback`
- targets may carry different metadata internally
- status and selection shapes remain the same
- session orchestration and frontend UX remain stable

That means the Windows port becomes an implementation task, not a contract redesign.
