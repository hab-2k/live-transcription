import type { SummaryView } from "../../lib/state/sessionReducer";

type SummaryScreenProps = {
  summary: SummaryView | null;
  loading?: boolean;
  onStartNewCall: () => void;
  onViewTranscript: () => void;
};

function SummaryList({ items, title }: { items: string[]; title: string }) {
  return (
    <section className="summary-section">
      <h2>{title}</h2>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function SummaryScreen({
  summary,
  loading = false,
  onStartNewCall,
  onViewTranscript,
}: SummaryScreenProps) {
  return (
    <main className="summary-shell">
      <section className="summary-card">
        <p className="eyebrow">Session complete</p>
        <h1>Call summary</h1>
        {loading ? (
          <p className="summary-loading">Generating summary…</p>
        ) : summary === null ? (
          <p className="summary-unavailable">
            After-call summary unavailable. You can still review the transcript or start a new
            call.
          </p>
        ) : (
          <>
            <section className="summary-recap">
              <h2>Call recap</h2>
              <p>{summary.recap}</p>
            </section>
            <div className="summary-grid">
              <SummaryList items={summary.strengths} title="Strengths" />
              <SummaryList items={summary.weaknesses} title="Weaknesses" />
              <SummaryList items={summary.flaggedMoments} title="Flagged moments" />
            </div>
          </>
        )}
        <div className="summary-actions">
          <button className="secondary-button" onClick={onViewTranscript} type="button">
            View transcript
          </button>
          <button className="ghost-button" onClick={onStartNewCall} type="button">
            Start new call
          </button>
        </div>
      </section>
    </main>
  );
}
