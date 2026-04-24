type ActionBarProps = {
  paused: boolean;
  onPauseCoaching: () => void;
  onStopSession: () => void;
};

export function ActionBar({ paused, onPauseCoaching, onStopSession }: ActionBarProps) {
  return (
    <section className="action-bar">
      <button className="secondary-button" onClick={onPauseCoaching} type="button">
        {paused ? "Resume Coaching" : "Pause Coaching"}
      </button>
      <button className="stop-button" onClick={onStopSession} type="button">
        Stop Session
      </button>
    </section>
  );
}
