import type { TranscriptEvent } from "../../lib/types/session";

type TranscriptPanelProps = {
  transcript: TranscriptEvent[];
};

function formatClock(value: string): string {
  return value.slice(11, 19);
}

function Lane({
  title,
  rows,
  emptyCopy,
}: {
  title: string;
  rows: TranscriptEvent[];
  emptyCopy: string;
}) {
  return (
    <section className="transcript-lane" aria-label={title}>
      <header className="lane-header">
        <h2>{title}</h2>
      </header>

      <div className="lane-body">
        {rows.length === 0 ? <p className="lane-empty">{emptyCopy}</p> : null}
        {rows.map((row, index) => (
          <article
            className={`transcript-row ${row.is_partial ? "transcript-row--partial" : ""}`}
            key={`${row.started_at}-${row.text}-${index}`}
          >
            <time className="transcript-time" dateTime={row.started_at}>
              {formatClock(row.started_at)}
            </time>
            <p>{row.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function TranscriptPanel({ transcript }: TranscriptPanelProps) {
  const colleagueRows = transcript.filter((row) => row.role === "colleague");
  const customerRows = transcript.filter((row) => row.role === "customer");
  const sharedRows = transcript.filter((row) => row.role === "shared" || row.role === "unknown");

  return (
    <section className="transcript-panel">
      <Lane
        emptyCopy="Waiting for colleague audio."
        rows={colleagueRows}
        title="Colleague audio"
      />
      <Lane emptyCopy="Waiting for customer audio." rows={customerRows} title="Customer audio" />
      {sharedRows.length > 0 ? (
        <Lane emptyCopy="Waiting for shared audio." rows={sharedRows} title="Shared audio" />
      ) : null}
    </section>
  );
}
