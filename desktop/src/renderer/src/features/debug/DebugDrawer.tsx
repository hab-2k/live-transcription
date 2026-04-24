import type { DebugLog } from "../../lib/state/sessionReducer";

type DebugDrawerProps = {
  enabled: boolean;
  open: boolean;
  logs: DebugLog[];
  onClose: () => void;
};

export function DebugDrawer({ enabled, open, logs, onClose }: DebugDrawerProps) {
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
