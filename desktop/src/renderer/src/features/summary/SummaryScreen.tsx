export type SummaryView = {
  strengths: string[];
  missedOpportunities: string[];
  flaggedMoments: string[];
};

type SummaryScreenProps = {
  summary: SummaryView;
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

export function SummaryScreen({ summary }: SummaryScreenProps) {
  return (
    <main className="summary-shell">
      <section className="summary-card">
        <p className="eyebrow">Session complete</p>
        <h1>Call summary</h1>
        <div className="summary-grid">
          <SummaryList items={summary.strengths} title="Strengths" />
          <SummaryList items={summary.missedOpportunities} title="Missed opportunities" />
          <SummaryList items={summary.flaggedMoments} title="Flagged moments" />
        </div>
      </section>
    </main>
  );
}
