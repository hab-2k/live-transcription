import { DebugDrawer } from "../debug/DebugDrawer";
import { ActionBar } from "./ActionBar";
import { MicIndicator } from "./MicIndicator";
import { NudgePanel } from "./NudgePanel";
import { TranscriptPanel } from "./TranscriptPanel";
import type { SessionState } from "../../lib/state/sessionReducer";
import type { TranscriptionConfig } from "../../lib/types/session";

type LiveScreenProps = {
  mode: "live" | "review";
  state: SessionState;
  onApplyTranscription: (config: TranscriptionConfig) => void;
  onBackToSetup: () => void;
  onBackToSummary: () => void;
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
  mode,
  state,
  onApplyTranscription,
  onBackToSetup,
  onBackToSummary,
  onPauseCoaching,
  onStopSession,
  onToggleDebug,
}: LiveScreenProps) {
  const inReview = mode === "review";

  return (
    <main className="live-shell">
      <header className="live-header">
        <div>
          <p className="eyebrow">{inReview ? "Session review" : "Session live"}</p>
          <h1>{inReview ? "Transcript review" : "Live coaching console"}</h1>
        </div>

        <div className="live-header__actions">
          {!inReview ? (
            <MicIndicator
              voiceActivity={state.voiceActivity}
              captureMode={state.setup.captureMode}
            />
          ) : null}
          <div className="session-pills" role="list">
            <span className="session-pill" role="listitem">
              {formatCaptureMode(state.setup.captureMode)}
            </span>
            <span className="session-pill" role="listitem">
              {formatPersona(state.setup.persona)}
            </span>
          </div>

          {state.debugEnabled && !inReview ? (
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
        <TranscriptPanel captureMode={state.setup.captureMode} transcript={state.transcript} />

        <aside className="live-sidepanel">
          {inReview ? (
            <section className="review-panel">
              <div className="panel-header">
                <h2>Ended session</h2>
              </div>
              <div className="nudge-list">
                <p className="panel-empty">
                  Review the final transcript, then go back to the summary or return to setup.
                </p>
              </div>
            </section>
          ) : (
            <NudgePanel nudges={state.nudges} />
          )}
          {inReview ? (
            <ActionBar
              mode="review"
              onBackToSetup={onBackToSetup}
              onBackToSummary={onBackToSummary}
            />
          ) : (
            <ActionBar
              mode="live"
              onPauseCoaching={onPauseCoaching}
              onStopSession={onStopSession}
              paused={state.coachingPaused}
            />
          )}
        </aside>
      </section>

      {!inReview ? (
        <DebugDrawer
          enabled={state.debugEnabled}
          logs={state.debugLogs}
          onClose={onToggleDebug}
          onApplyTranscription={onApplyTranscription}
          open={state.debugOpen}
          transcription={state.setup.transcription}
        />
      ) : null}
    </main>
  );
}
