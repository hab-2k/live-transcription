type LiveActionBarProps = {
  mode: "live";
  paused: boolean;
  onPauseCoaching: () => void;
  onStopSession: () => void;
};

type ReviewActionBarProps = {
  mode: "review";
  onBackToSetup: () => void;
  onBackToSummary: () => void;
};

type ActionBarProps = LiveActionBarProps | ReviewActionBarProps;

export function ActionBar(props: ActionBarProps) {
  if (props.mode === "review") {
    return (
      <section className="action-bar action-bar--review">
        <p className="action-bar__copy">
          Transcript review is read-only. Go back to the summary or return to setup to start a new
          call.
        </p>
        <button className="secondary-button" onClick={props.onBackToSummary} type="button">
          Back to summary
        </button>
        <button className="ghost-button" onClick={props.onBackToSetup} type="button">
          Back to setup
        </button>
      </section>
    );
  }

  return (
    <section className="action-bar">
      <button className="secondary-button" onClick={props.onPauseCoaching} type="button">
        {props.paused ? "Resume Coaching" : "Pause Coaching"}
      </button>
      <button className="stop-button" onClick={props.onStopSession} type="button">
        Stop Session
      </button>
    </section>
  );
}
