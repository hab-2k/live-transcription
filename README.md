# Live Transcription Demo

Desktop demo for live transcription, dual-source capture, and colleague-facing coaching.

## Stack

- `Electron + React` desktop shell
- Local `FastAPI` backend
- Replaceable ASR provider contract with `parakeet_unified` as the default backend
- `silero-vad` backed segmentation controls
- OpenAI-compatible LLM adapter for local or remote coaching endpoints

## Current Status

- `mic only` mode produces revisable `transcript_turn` events in the shared lane
- `mic + BlackHole` mode maps `microphone -> colleague audio` and `BlackHole -> customer audio`
- provider output is normalized in the backend before the renderer sees it
- the renderer updates turns in place by `turn_id` / `revision`
- setup and live debug surfaces expose dev-only provider, segmentation, coaching-window, and VAD controls
- live reconfiguration restarts only the active transcription pipeline for the session

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

# Default provider
LTD_DEFAULT_ASR_PROVIDER=parakeet_unified

# Parakeet Unified runtime
LTD_PARAKEET_MODEL_PATH=/absolute/path/to/parakeet-unified-en-0.6b.nemo
LTD_PARAKEET_PYTHON_EXECUTABLE=/Users/habeeb/dev/repos/live-transcription-demo/.cache/nemo312/.venv/bin/python
LTD_PARAKEET_MIN_AUDIO_SECS=1.6
LTD_PARAKEET_DECODE_HOP_SECS=1.6

# Optional NeMo fallback
LTD_NEMO_MODEL_PATH=
LTD_NEMO_PYTHON_EXECUTABLE=

# Backend-managed transcription defaults
LTD_TRANSCRIPTION_LATENCY_PRESET=balanced
LTD_TRANSCRIPTION_SEGMENTATION_POLICY=source_turns
LTD_TRANSCRIPTION_COACHING_WINDOW_POLICY=finalized_turns
LTD_TRANSCRIPTION_VAD_PROVIDER=silero_vad
LTD_TRANSCRIPTION_VAD_THRESHOLD=0.5
LTD_TRANSCRIPTION_VAD_MIN_SILENCE_MS=600

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

- The backend now normalizes all ASR output into `transcript_turn` events before broadcasting.
- `parakeet_unified` is the default provider, but the session runtime can swap to another provider without frontend changes.
- The backend process stays on the lighter app environment while spawning a persistent local sidecar via `LTD_PARAKEET_PYTHON_EXECUTABLE`.
- The sidecar loads the model once per provider lifecycle instead of restoring it for every decode window.
- Session startup and live reconfiguration both accept the same normalized transcription config shape.
- If `LTD_PARAKEET_MODEL_PATH` is unset or points to the wrong file, session start will fail fast with a provider-specific backend error.
- The backend logs session API requests, provider startup, transcription reconfiguration, decode activity, and outbound LLM calls at `INFO` level.
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

## Benchmark Harness

The repo keeps a provider-aware buffered benchmark harness in `backend/scripts/benchmark_nemo_streaming.py`.

Run:

```bash
.cache/nemo312/.venv/bin/python backend/scripts/benchmark_nemo_streaming.py \
  --provider parakeet_unified \
  --model-path "$PARAKEET_MODEL_PATH" \
  --audio fixtures/audio/benchmark_call.wav
```

The harness still uses NeMo's buffered utilities under the hood for both `nemo` and `parakeet_unified`, but the output is labeled by provider so you can compare runtime settings more honestly.
