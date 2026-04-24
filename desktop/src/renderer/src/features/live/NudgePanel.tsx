import type { CoachingNudgeEvent } from "../../lib/types/session";

type NudgePanelProps = {
  nudges: CoachingNudgeEvent[];
};

function formatClock(value: string): string {
  return value.slice(11, 19);
}

export function NudgePanel({ nudges }: NudgePanelProps) {
  return (
    <section className="nudge-panel">
      <div className="panel-header">
        <h2>Live nudges</h2>
      </div>

      <div className="nudge-list">
        {nudges.length === 0 ? <p className="panel-empty">Live coaching will appear here.</p> : null}
        {nudges.map((nudge) => (
          <article className="nudge-card" key={`${nudge.timestamp}-${nudge.title}`}>
            <div className="nudge-card__header">
              <strong>{nudge.title}</strong>
              <time className="nudge-card__time" dateTime={nudge.timestamp}>
                {formatClock(nudge.timestamp)}
              </time>
            </div>
            <p>{nudge.message}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
