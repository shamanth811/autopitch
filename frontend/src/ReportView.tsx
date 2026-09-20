import { useState } from "react";
import { Link } from "react-router-dom";
import { cap, pct, usd, words } from "./format";
import type { FormDStats, Report, SectionScore } from "./types";

function download(report: Report) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report.deck.company.replace(/\W+/g, "-").toLowerCase()}-analysis.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// Source URLs come from the index; only ever link http(s).
function safeHref(u: string): string | undefined {
  try {
    const { protocol } = new URL(u);
    return protocol === "https:" || protocol === "http:" ? u : undefined;
  } catch {
    return undefined;
  }
}

function RaiseRange({ f, ask }: { f: FormDStats; ask: number | null }) {
  const marks = [
    ["25th percentile", f.p25_usd],
    ["Median", f.median_usd],
    ["75th percentile", f.p75_usd],
    ["90th percentile", f.p90_usd],
  ] as const;
  return (
    <div className="range">
      <dl>
        {marks.map(([label, v]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{usd(v)}</dd>
          </div>
        ))}
        <div className="ask">
          <dt>Your ask</dt>
          <dd>
            {usd(ask)}
            {f.ask_percentile !== null && (
              <span className="muted"> · {Math.round(f.ask_percentile)}th percentile</span>
            )}
          </dd>
        </div>
      </dl>
      {f.ask_percentile !== null && (
        <div
          className="pct-bar"
          role="img"
          aria-label={`The ask is larger than ${Math.round(f.ask_percentile)}% of raises`}
        >
          <span style={{ left: `${Math.min(99, Math.max(1, f.ask_percentile))}%` }} />
        </div>
      )}
    </div>
  );
}

function SectionRow({ s, weight, weak }: { s: SectionScore; weight?: number; weak: boolean }) {
  return (
    <details className="section">
      <summary>
        <span className="sec-name">
          {cap(s.section)}
          {weak && <span className="tag">Weak</span>}
        </span>
        <span className="bar" aria-hidden>
          <span style={{ width: `${s.score * 10}%` }} />
        </span>
        <span className="sec-score">{s.score.toFixed(1)}</span>
        <span className="muted sec-weight">{weight === undefined ? "excluded" : pct(weight)}</span>
      </summary>
      <p className="serif">{s.summary}</p>
      <ul className="criteria">
        {s.criteria.map((c) => (
          <li key={c.criterion}>
            <strong>{words(c.criterion)}</strong>{" "}
            <span className="muted">{c.score}/10</span>
            <p className="serif">{c.reasoning}</p>
          </li>
        ))}
        {s.missing_data.map((m) => (
          <li key={m} className="muted">
            Missing: {m}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ReportView({ report: r, onDelete }: { report: Report; onDelete: () => void }) {
  const b = r.benchmark;
  const [confirming, setConfirming] = useState(false);
  return (
    <article className="report">
      <p className="eyebrow">
        {r.deck.sector} · {r.deck.stage ?? "stage unknown"}
      </p>
      <h1>{r.deck.company}</h1>
      {r.deck.one_liner && <p className="lead">{r.deck.one_liner}</p>}

      <div className="composite">
        <span className="big">{r.composite.score.toFixed(1)}</span>
        <span className="muted">/ 10 composite</span>
      </div>
      {r.composite.excluded.length > 0 && (
        <p className="muted">
          Not scored, weights renormalised: {r.composite.excluded.map(cap).join(", ")}.
        </p>
      )}

      <div className="row noprint">
        <Link to="/analyze" className="btn primary">
          Analyze another deck
        </Link>
        <button className="btn outline" onClick={() => download(r)}>
          Download JSON
        </button>
        <button className="btn outline" onClick={() => window.print()}>
          Print / save PDF
        </button>
        {confirming ? (
          <>
            <button className="btn outline danger" onClick={onDelete}>
              Confirm delete
            </button>
            <button className="btn outline" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button className="btn outline" onClick={() => setConfirming(true)}>
            Delete report
          </button>
        )}
      </div>

      <h2>Section scores</h2>
      <div className="sections">
        {r.sections.map((s) => (
          <SectionRow
            key={s.section}
            s={s}
            weight={r.composite.weights[s.section]}
            weak={r.weak_sections.includes(s.section)}
          />
        ))}
      </div>

      {b?.formd && (
        <>
          <h2>Raise size against SEC Form D filings</h2>
          {b.formd.median_usd !== null ? (
            <>
              <p className="serif">
                {b.formd.peers.toLocaleString()} private raises by companies under five years old
                in {b.formd.industries.join(", ")}, filed {b.formd.period_start} to{" "}
                {b.formd.period_end}.
              </p>
              <RaiseRange f={b.formd} ask={r.deck.financials.raise_amount_usd} />
            </>
          ) : (
            <p className="serif">Not enough comparable filings to show a distribution.</p>
          )}
          {b.formd.flags.map((f) => (
            <p key={f} className="flag">
              {f}
            </p>
          ))}
          <p className="muted">
            Form D reports the amount sold so far and has no funding stage, so this compares size
            only, across all stages.
          </p>
        </>
      )}

      {b && (b.comparables.length > 0 || b.flags.length > 0) && (
        <>
          <h2>Similar companies in SEC S-1 filings</h2>
          {b.median_raise_usd !== null && (
            <p className="serif">
              Median comparable raise {usd(b.median_raise_usd)} against a deck ask of{" "}
              {usd(r.deck.financials.raise_amount_usd)}
              {b.raise_ratio !== null && ` (${b.raise_ratio}×)`}, from {b.stage_comparables}{" "}
              same-stage comparables with a disclosed amount.
            </p>
          )}
          {b.flags.map((f) => (
            <p key={f} className="flag">
              {f}
            </p>
          ))}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Stage</th>
                  <th className="num">Amount</th>
                  <th className="num">Year</th>
                  <th className="num">Match</th>
                </tr>
              </thead>
              <tbody>
                {b.comparables.map((m) => {
                  const href = safeHref(m.pattern.source_url);
                  return (
                    <tr key={m.pattern.id}>
                      <td>
                        {href ? (
                          <a href={href} target="_blank" rel="noopener noreferrer">
                            {m.pattern.company}
                          </a>
                        ) : (
                          m.pattern.company
                        )}
                      </td>
                      <td>{m.pattern.stage ?? "n/a"}</td>
                      <td className="num">{usd(m.pattern.round_amount_usd)}</td>
                      <td className="num">{m.pattern.year ?? "n/a"}</td>
                      <td className="num">{m.similarity.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {r.objections.length > 0 && (
        <>
          <h2>Likely investor objections</h2>
          <ol className="objections">
            {r.objections.map((o) => (
              <li key={o.question}>
                <p className="eyebrow">{o.section}</p>
                <h3>{o.question}</h3>
                <p className="serif">
                  <strong>Basis.</strong> {o.basis}
                </p>
                <p className="serif">
                  <strong>Bring.</strong> {o.suggested_response}
                </p>
              </li>
            ))}
          </ol>
        </>
      )}

      <details className="trace">
        <summary>Reasoning trace ({r.composite.trace.length} criteria)</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Section</th>
                <th>Criterion</th>
                <th className="num">Score</th>
                <th className="num">Weight</th>
              </tr>
            </thead>
            <tbody>
              {r.composite.trace.map((t) => (
                <tr key={`${t.section}-${t.criterion}`}>
                  <td>{cap(t.section)}</td>
                  <td>{words(t.criterion)}</td>
                  <td className="num">{t.score}</td>
                  <td className="num">{(t.effective_weight * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p className="muted disclaimer">{r.disclaimer}</p>
    </article>
  );
}
