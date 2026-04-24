import type { VoiceActivity } from "../../lib/state/sessionReducer";

type MicIndicatorProps = {
  voiceActivity: VoiceActivity;
  captureMode: "mic_only" | "mic_plus_blackhole";
};

function Indicator({ label, level, active }: { label: string; level: number; active: boolean }) {
  return (
    <div className={`mic-indicator ${active ? "mic-indicator--active" : ""}`}>
      <div className="mic-indicator__bar">
        <div
          className="mic-indicator__fill"
          style={{ width: `${Math.round(level * 100)}%` }}
        />
      </div>
      <span className="mic-indicator__label">{label}</span>
    </div>
  );
}

export function MicIndicator({ voiceActivity, captureMode }: MicIndicatorProps) {
  return (
    <div className="mic-indicators" role="status" aria-label="Voice activity">
      <Indicator
        label={captureMode === "mic_only" ? "Mic" : "Colleague"}
        level={voiceActivity.microphone.level}
        active={voiceActivity.microphone.active}
      />
      {captureMode === "mic_plus_blackhole" && (
        <Indicator
          label="Customer"
          level={voiceActivity.blackhole.level}
          active={voiceActivity.blackhole.active}
        />
      )}
    </div>
  );
}
