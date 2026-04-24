import { DebugDrawer } from "../debug/DebugDrawer";
import { ActionBar } from "./ActionBar";
import { MicIndicator } from "./MicIndicator";
import { NudgePanel } from "./NudgePanel";
import { TranscriptPanel } from "./TranscriptPanel";
import type { SessionState } from "../../lib/state/sessionReducer";
import type { TranscriptionConfig } from "../../lib/types/session";

type LiveScreenProps = {
  state: SessionState;
  onApplyTranscription: (config: TranscriptionConfig) => void;
  onPauseCoaching: () => void;
  onStopSession: () => void;
  onToggleDebug: () => void;
};

function formatCaptureMode(value: SessionState["setup"]["captureMode"]): string {
  return value === "mic_only" ? "Microphone only" : "Microphone + BlackHole";
}

function formatPersona(value: SessionState["setup"]["persona"]): string {
  return value === "manager" ? "Manager" : "Colleague contact";
}

export function LiveScreen({
  state,
  onApplyTranscription,
  onPauseCoaching,
  onStopSession,
  onToggleDebug,
}: LiveScreenProps) {
  return (
    <main className="live-shell">
      <header className="live-header">
        <div>
          <p className="eyebrow">Session live</p>
          <h1>Live coaching console</h1>
        </div>

        <div className="live-header__actions">
          <MicIndicator
            voiceActivity={state.voiceActivity}
            captureMode={state.setup.captureMode}
          />
          <div className="session-pills" role="list">
            <span className="session-pill" role="listitem">
              {formatCaptureMode(state.setup.captureMode)}
            </span>
            <span className="session-pill" role="listitem">
              {formatPersona(state.setup.persona)}
            </span>
          </div>

          {state.debugEnabled ? (
            <button
              aria-label={state.debugOpen ? "Close debug menu" : "Open debug menu"}
              className="menu-button"
              onClick={onToggleDebug}
              type="button"
            >
              <span />
              <span />
              <span />
            </button>
          ) : null}
        </div>
      </header>

      <section className="live-layout">
        <TranscriptPanel transcript={state.transcript} />

        <aside className="live-sidepanel">
          <NudgePanel nudges={state.nudges} />
          <ActionBar
            onPauseCoaching={onPauseCoaching}
            onStopSession={onStopSession}
            paused={state.coachingPaused}
          />
        </aside>
      </section>

      <DebugDrawer
        enabled={state.debugEnabled}
        logs={state.debugLogs}
        onClose={onToggleDebug}
        onApplyTranscription={onApplyTranscription}
        open={state.debugOpen}
        transcription={state.setup.transcription}
      />
    </main>
  );
}
