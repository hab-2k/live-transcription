# Live Transcription Demo

Desktop demo for live transcription, coaching nudges, and after-call summary/review flows.

## Stack

- `Electron + React` desktop shell
- Local `FastAPI` backend with session/websocket APIs
- Swappable ASR provider runtime (`parakeet_unified` default, `nemo` supported)
- `silero-vad` segmentation controls
- OpenAI-compatible LLM client for live nudges and after-call summaries
- Native macOS system-audio capture helper (`Swift` Core Audio Process Tap CLI)

## Current Behavior

- Setup screen supports `microphone only` and `microphone + system audio` capture.
- In `microphone + system audio`, you pick a target app process from the setup form.
- Backend normalizes provider output into `transcript_turn` events before broadcast.
- Renderer reconciles turn updates by `turn_id` and `revision`.
- Live screen supports pause coaching, stop session, and developer debug controls.
- Session stop returns an after-call summary; ended sessions can switch between summary and transcript review screens.

## Local Setup

### Prerequisites

- macOS (required for native system audio capture path)
- Python `3.10+`
- Node.js (with `corepack` enabled)
- `uv`
- `swift` toolchain (for `system-audio-capture`)

### 1) Backend

```bash
uv venv backend/.venv --python 3.10
uv pip install --python backend/.venv/bin/python -e "backend[dev]"
```

### 2) Desktop

```bash
corepack pnpm --dir desktop install
```

### 3) Native system-audio helper (macOS)

Build the Swift helper used by `/api/capturable-apps` and `mic_plus_system` sessions:

```bash
cd native/macos/SystemAudioCapture && swift build
```

If this binary is not built, capturable apps list will be empty and system-audio capture cannot start.

### 4) Environment config

Copy `.env.example` to `.env` and update values for your machine:

```bash
cp .env.example .env
```

Key settings:

- `LTD_PARAKEET_MODEL_PATH`: required for `parakeet_unified`
- `LTD_PARAKEET_PYTHON_EXECUTABLE`: optional sidecar Python for Parakeet/NeMo runtime
- `LTD_NEMO_MODEL_PATH`: optional fallback provider model
- `LTD_LLM_BASE_URL`, `LTD_LLM_MODEL`, `LTD_LLM_API_KEY`: coaching LLM endpoint
- `LTD_SUMMARY_LLM_MODEL`: optional override model for after-call summary generation
- `LTD_LOG_LEVEL`: backend log verbosity

Any OpenAI-compatible endpoint works (`Ollama`, `LM Studio`, `vLLM`, OpenAI, etc.).

Set `VITE_ENABLE_DEBUG_DRAWER=false` to disable developer debug controls in the renderer.

## Running the App

Start backend and desktop in separate terminals:

```bash
# Terminal 1
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

```bash
# Terminal 2
corepack pnpm --dir desktop dev
```

The Electron app connects to `http://localhost:8000` by default.

To point desktop at a different backend URL:

```bash
LTD_BACKEND_URL=http://127.0.0.1:8010 corepack pnpm --dir desktop dev
```

## Backend API

Base URL: `http://localhost:8000`

- `GET /api/devices` - list available audio devices for setup.
- `GET /api/capturable-apps` - list running apps eligible for system-audio capture (macOS helper required).
- `POST /api/sessions` - start a session and return `session_id`.
- `WS /api/sessions/{session_id}/events` - stream normalized session events (`transcript_turn`, nudges, status, voice activity).
- `POST /api/sessions/{session_id}/pause-coaching` - pause or resume coaching nudges.
- `POST /api/sessions/{session_id}/transcription-config` - apply live transcription/provider/VAD config updates.
- `POST /api/sessions/{session_id}/stop` - stop session and return after-call summary payload.

## Running Tests

```bash
backend/.venv/bin/pytest backend/tests -v
corepack pnpm --dir desktop test
```

Optional e2e:

```bash
corepack pnpm --dir desktop test:e2e
```

## Benchmark Harness

Provider-aware benchmark script:

```bash
backend/scripts/benchmark_nemo_streaming.py
```

Example:

```bash
.cache/nemo312/.venv/bin/python backend/scripts/benchmark_nemo_streaming.py \
  --provider parakeet_unified \
  --model-path "$PARAKEET_MODEL_PATH" \
  --audio fixtures/audio/benchmark_call.wav
```
