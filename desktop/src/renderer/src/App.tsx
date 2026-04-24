import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { LiveScreen } from "./features/live/LiveScreen";
import { SetupScreen } from "./features/setup/SetupScreen";
import { SummaryScreen } from "./features/summary/SummaryScreen";
import {
  connectSessionEvents,
  getBackendUrl,
  setCoachingPaused,
  startSession,
  stopSession,
} from "./lib/api/client";
import {
  createInitialSessionState,
  sessionReducer,
  type SessionSetup,
} from "./lib/state/sessionReducer";
import "./styles/tokens.css";
import "./styles/app.css";

const DEBUG_DRAWER_ENABLED = import.meta.env.VITE_ENABLE_DEBUG_DRAWER !== "false";
const BACKEND_URL = getBackendUrl();

export default function App() {
  const [state, dispatch] = useReducer(
    sessionReducer,
    DEBUG_DRAWER_ENABLED,
    createInitialSessionState,
  );
  const [startError, setStartError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const disconnectRef = useRef<(() => void) | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const handleStart = useCallback(async (setup: SessionSetup) => {
    setStartError(null);
    setStarting(true);

    try {
      const { session_id } = await startSession(setup, BACKEND_URL);
      dispatch({ type: "start_session", setup });
      sessionIdRef.current = session_id;

      disconnectRef.current = connectSessionEvents(
        session_id,
        (event) => dispatch({ type: "ingest_event", event }),
        BACKEND_URL,
      );
    } catch (err) {
      console.error("Failed to start session:", err);
      setStartError(err instanceof Error ? err.message : "Failed to start session.");
    } finally {
      setStarting(false);
    }
  }, []);

  const handleStop = useCallback(async () => {
    if (sessionIdRef.current) {
      try {
        const response = await stopSession(sessionIdRef.current, BACKEND_URL);
        dispatch({ type: "complete_session", summary: response.summary });
      } catch (err) {
        console.error("Failed to stop session:", err);
      }
    }
    disconnectRef.current?.();
    disconnectRef.current = null;
    sessionIdRef.current = null;
  }, []);

  const handlePauseCoaching = useCallback(async () => {
    if (!sessionIdRef.current) {
      return;
    }

    try {
      await setCoachingPaused(sessionIdRef.current, !state.coachingPaused, BACKEND_URL);
    } catch (err) {
      console.error("Failed to update coaching pause state:", err);
    }
  }, [state.coachingPaused]);

  useEffect(() => {
    return () => {
      disconnectRef.current?.();
    };
  }, []);

  if (state.status === "setup") {
    return <SetupScreen errorMessage={startError} isStarting={starting} onStart={handleStart} />;
  }

  if (state.status === "ended" && state.summary !== null) {
    return <SummaryScreen summary={state.summary} />;
  }

  return (
    <LiveScreen
      onPauseCoaching={handlePauseCoaching}
      onStopSession={handleStop}
      onToggleDebug={() => dispatch({ type: "toggle_debug" })}
      state={state}
    />
  );
}
