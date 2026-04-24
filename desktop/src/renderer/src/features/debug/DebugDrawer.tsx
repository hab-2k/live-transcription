import { useEffect, useState } from "react";

import type { DebugLog } from "../../lib/state/sessionReducer";
import type { TranscriptionConfig } from "../../lib/types/session";
import { TranscriptionSettingsFields } from "../transcription/TranscriptionSettingsFields";

type DebugDrawerProps = {
  enabled: boolean;
  open: boolean;
  logs: DebugLog[];
  transcription?: TranscriptionConfig;
  onApplyTranscription?: (config: TranscriptionConfig) => void;
  onClose: () => void;
};

export function DebugDrawer({
  enabled,
  open,
  logs,
  transcription,
  onApplyTranscription,
  onClose,
}: DebugDrawerProps) {
  const [draftConfig, setDraftConfig] = useState<TranscriptionConfig | null>(transcription ?? null);

  useEffect(() => {
    setDraftConfig(transcription ?? null);
  }, [transcription, open]);

  if (!enabled || !open) {
    return null;
  }

  return (
    <aside aria-label="Debug panel" className="debug-drawer">
      <div className="debug-drawer__header">
        <h2>Debug panel</h2>
        <button className="ghost-button" onClick={onClose} type="button">
          Close
        </button>
      </div>

      <section className="debug-section">
        <h3>Devices</h3>
        <p>Inspect source routing, stream health, and loopback state.</p>
      </section>

      <section className="debug-section">
        <h3>Coaching engine</h3>
        <p>Review endpoint selection, recent rule output, and coaching activity.</p>
      </section>

      <section className="debug-section">
        <h3>Noise control</h3>
        <p>Keep preprocessing and signal diagnostics out of the colleague-facing view.</p>
      </section>

      {draftConfig !== null ? (
        <section className="debug-section">
          <h3>Transcription settings</h3>
          <p>Adjust provider, segmentation, and Silero VAD settings without restarting the app.</p>
          <TranscriptionSettingsFields config={draftConfig} onChange={setDraftConfig} />
          <button
            className="ghost-button"
            onClick={() => onApplyTranscription?.(draftConfig)}
            type="button"
          >
            Apply transcription settings
          </button>
        </section>
      ) : null}

      <section className="debug-section">
        <h3>Recent events</h3>
        <ul className="debug-log-list">
          {logs.length === 0 ? <li>No debug events yet.</li> : null}
          {logs.map((log) => (
            <li key={log.id}>
              <strong>{log.label}</strong>
              <span>{log.message}</span>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
