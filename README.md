# Live Transcription Demo

Desktop demo for live transcription, dual-source capture, and colleague-facing coaching.

## Stack

- `Electron + React` desktop shell
- Local `FastAPI` backend
- Replaceable ASR provider contract with `NeMo` as the default backend
- OpenAI-compatible LLM adapter for local or remote coaching endpoints

## Current Status

- `mic only` mode produces normalized `shared` transcript events
- `mic + BlackHole` mode maps `microphone -> colleague audio` and `BlackHole -> customer audio`
- live nudges, rule flags, debug drawer, and after-call summary scaffolding are implemented
- the renderer only consumes normalized session events and does not depend on NeMo-specific payloads

## Local Setup

### Backend

Use `uv` and Python `3.10` for the app/test environment:

```bash
uv venv backend/.venv -p /Users/habeeb/.local/share/uv/python/cpython-3.10.18-macos-aarch64-none/bin/python3.10 --clear --seed
uv pip install --python backend/.venv/bin/python -e "backend[dev]"
```

### Desktop

```bash
corepack pnpm --dir desktop install
```

### macOS audio

- Install `BlackHole 2ch`
- In dual-source mode, route call audio to `BlackHole`
- Use the colleague microphone as the `microphone` input source

### Backend config

Create a `.env` file in the project root with your ASR and LLM settings:

```bash
# Backend app logging
LTD_LOG_LEVEL=INFO

# NeMo ASR runtime
LTD_NEMO_MODEL_PATH=/absolute/path/to/parakeet-tdt-0.6b-v2.nemo

# Recommended on this Mac: use the separate Python 3.12 NeMo env as a local sidecar
LTD_NEMO_PYTHON_EXECUTABLE=/Users/habeeb/dev/repos/live-transcription-demo/.cache/nemo312/.venv/bin/python

# Buffered decode cadence for the pseudo-live local path
LTD_NEMO_MIN_AUDIO_SECS=1.0
LTD_NEMO_DECODE_HOP_SECS=8.0

# Required if your endpoint needs an API key (OpenAI, Anthropic, etc.)
LTD_LLM_API_KEY=sk-your-key-here

# Defaults shown — override as needed
LTD_LLM_BASE_URL=http://localhost:11434/v1
LTD_LLM_MODEL=local-model
```

Any OpenAI-compatible endpoint works:

- local `Ollama` via `http://localhost:11434/v1`
- `LM Studio`, `vLLM`, or another compatible local server
- OpenAI directly via `https://api.openai.com/v1` with your API key
- any remote provider exposing the OpenAI chat-completions shape

Set `VITE_ENABLE_DEBUG_DRAWER=false` to remove debug access from the renderer.

## ASR Runtime Notes

- The backend capture/session path is wired to a real `NeMo` provider now.
- On this machine, the provider uses a buffered pseudo-live path rather than true low-latency streaming.
- The backend process stays on the lighter app environment while spawning a persistent local `NeMo` sidecar via `LTD_NEMO_PYTHON_EXECUTABLE`.
- The sidecar loads the model once per session/provider lifecycle instead of restoring it for every decode window.
- If `LTD_NEMO_MODEL_PATH` is unset or points to the wrong file, session start will fail fast with a clear backend error.
- The backend now logs session API requests, NeMo worker/model activity, per-source ASR transcription start/stop, decode activity, and outbound LLM calls at `INFO` level.
- If you want more or less verbosity, set `LTD_LOG_LEVEL` in `.env`.

## Running the App

Start the backend and desktop app in two terminals:

```bash
# Terminal 1 — backend
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

Backend logs now print directly in that terminal.

```bash
# Terminal 2 — desktop
corepack pnpm --dir desktop dev
```

The Electron app will open and connect to the backend at `http://localhost:8000`.

If you need the desktop shell to point at a different backend host or port at runtime, set `LTD_BACKEND_URL` before launch:

```bash
LTD_BACKEND_URL=http://127.0.0.1:8010 corepack pnpm --dir desktop dev
```

## Running Tests

```bash
backend/.venv/bin/pytest backend/tests -v
corepack pnpm --dir desktop test -- run
```

## NeMo Benchmark Gate

The buffered `parakeet-tdt-0.6b-v2` path was validated against a separate Python `3.12` probe env with newer `NeMo` utilities than the initial backend env.

Run:

```bash
.cache/nemo312/.venv/bin/python backend/scripts/benchmark_nemo_streaming.py \
  --provider nemo \
  --model-path "$PARAKEET_MODEL_PATH" \
  --audio fixtures/audio/benchmark_call.wav
```

Measured on this Mac:

- `realtime_factor`: about `2.18`
- `mean_partial_latency_ms`: about `5747`
- `final_latency_ms`: about `17682`

That means the local CPU path is functional but not good enough for true live production coaching on this machine. The app keeps `NeMo` as the default provider behind a stable contract so the runtime can be swapped later without rewriting the UI.
