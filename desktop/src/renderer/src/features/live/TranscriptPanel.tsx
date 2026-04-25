import { useEffect, useRef, useState } from "react";
import type { CaptureMode } from "../../lib/state/sessionReducer";
import type { TranscriptTurnEvent } from "../../lib/types/session";

function formatClock(value: string): string {
  return value.slice(11, 19);
}

function Lane({
  title,
  rows,
  emptyCopy,
}: {
  title: string;
  rows: TranscriptTurnEvent[];
  emptyCopy: string;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [showFade, setShowFade] = useState(false);

  useEffect(() => {
    const el = bodyRef.current;
    if (!el) return;

    const checkFade = () => {
      setShowFade(el.scrollTop > 20);
    };

    el.addEventListener("scroll", checkFade, { passive: true });
    checkFade();
    return () => el.removeEventListener("scroll", checkFade);
  }, []);

  // Newest first in DOM; column-reverse places them at the bottom.
  const ordered = [...rows].reverse();

  return (
    <section className="transcript-lane" aria-label={title}>
      <header className="lane-header">
        <h2>{title}</h2>
      </header>

      <div className="transcript-viewport">
        {showFade ? <div className="transcript-fade" /> : null}
        <div ref={bodyRef} className="lane-body">
          {ordered.length === 0 ? <p className="lane-empty">{emptyCopy}</p> : null}
          {ordered.map((row) => (
            <article
              className={`transcript-row ${row.is_final ? "" : "transcript-row--partial"}`}
              key={row.turn_id}
            >
              <time className="transcript-time" dateTime={row.started_at}>
                {formatClock(row.started_at)}
              </time>
              <p>{row.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function TranscriptPanel({ captureMode, transcript }: TranscriptPanelProps) {
  if (captureMode === "mic_only") {
    return (
      <section className="transcript-panel transcript-panel--single">
        <Lane
          emptyCopy="Waiting for live transcript."
          rows={transcript}
          title="Live Transcript"
        />
      </section>
    );
  }

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
