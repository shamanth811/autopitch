import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ConfirmDialog } from "./ConfirmDialog";
import { cap, pct, TONE_LABEL, tone, usd, words } from "./format";
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
      {f.ask_percentile !== null && (
        <div className="pct-ticks muted" aria-hidden>
          <span>Smallest raises</span>
          <span>Median</span>
          <span>Largest raises</span>
        </div>
      )}
    </div>
  );
}

function SectionRow({
  s,
  weight,
  weak,
  open,
}: {
  s: SectionScore;
  weight?: number;
  weak: boolean;
  open: boolean;
}) {
  const t = tone(s.score, weak);
  return (
    <details className="section" open={open}>
      <summary>
        <span className="sec-name">
          {cap(s.section)}
          <span className={`tag ${t}`}>{TONE_LABEL[t]}</span>
        </span>
        <span className="bar" aria-hidden>
          <span className={t} style={{ width: `${s.score * 10}%` }} />
        </span>
        <span className="sec-score">{s.score.toFixed(1)}</span>
        <span className="muted sec-weight">{weight === undefined ? "excluded" : pct(weight)}</span>
      </summary>
      <p className="serif">{s.summary}</p>
      <ul className="criteria">
        {s.criteria.map((c) => (
          <li key={c.criterion}>
            <strong>{words(c.criterion)}</strong> <span className="muted">{c.score}/10</span>
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

function Verdict({ r }: { r: Report }) {
  const ranked = [...r.sections].sort((a, b) => a.score - b.score);
  const weakest = ranked.slice(0, 2);
  const best = ranked[ranked.length - 1];
  const pctile = r.benchmark?.formd?.ask_percentile;
  const top = r.objections[0];
  if (!best) return null;
  return (
    <section className="verdict" aria-label="Summary">
      <div>
        <p className="eyebrow">Strongest</p>
        <p className="v-main">
          {cap(best.section)} <span className="muted">{best.score.toFixed(1)}</span>
        </p>
      </div>
      <div>
        <p className="eyebrow">Fix first</p>
        <p className="v-main">
          {weakest.map((w) => `${cap(w.section)} ${w.score.toFixed(1)}`).join(" · ")}
        </p>
      </div>
      {pctile !== null && pctile !== undefined && (
        <div>
          <p className="eyebrow">Your ask</p>
          <p className="v-main">Larger than {Math.round(pctile)}% of raises</p>
        </div>
      )}
      {top && (
        <div className="v-wide">
          <p className="eyebrow">Expect this question</p>
          <p className="v-main serif">{top.question}</p>
        </div>
      )}
    </section>
  );
}

export function ReportView({ report: r, onDelete }: { report: Report; onDelete: () => void }) {
  const b = r.benchmark;
  const [confirming, setConfirming] = useState(false);
  // null = each section follows its default (weak ones open); boolean = user override.
  const [openAll, setOpenAll] = useState<boolean | null>(null);
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const on = () => setPrinting(true);
    const off = () => setPrinting(false);
    window.addEventListener("beforeprint", on);
    window.addEventListener("afterprint", off);
    return () => {
      window.removeEventListener("beforeprint", on);
      window.removeEventListener("afterprint", off);
    };
  }, []);
  const overall = tone(r.composite.score);
  return (
    <article className={`report${printing ? " printing" : ""}`}>
      <p className="eyebrow">
        {r.deck.sector} · {r.deck.stage ?? "stage unknown"}
      </p>
      <h1>{r.deck.company}</h1>
      {r.deck.one_liner && <p className="lead">{r.deck.one_liner}</p>}

      <div className="composite">
        <span className={`big ${overall}`}>{r.composite.score.toFixed(1)}</span>
        <span className="muted">/ 10 composite</span>
        <span className={`tag ${overall}`}>{TONE_LABEL[overall]}</span>
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
        <button className="btn outline" onClick={() => setConfirming(true)}>
          Delete report
        </button>
      </div>

      <Verdict r={r} />

      <h2 className="h2-row">
        Section scores
        <button
          className="link-btn noprint"
          onClick={() => setOpenAll(openAll === true ? false : true)}
        >
          {openAll === true ? "Collapse all" : "Expand all"}
        </button>
      </h2>
      <div className="sections">
        {r.sections.map((s) => (
          <SectionRow
            key={`${s.section}-${openAll}`}
            open={printing || (openAll ?? r.weak_sections.includes(s.section))}
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
                {b.formd.peers.toLocaleString()} private raises by companies under five years old in{" "}
                {b.formd.industries.join(", ")}, filed {b.formd.period_start} to{" "}
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
            <table className="stack">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Stage</th>
                  <th className="num">Amount</th>
                  <th className="num">Year</th>
                  <th className="num">Similarity</th>
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
                      <td data-label="Stage">{m.pattern.stage ?? "n/a"}</td>
                      <td className="num" data-label="Amount">
                        {usd(m.pattern.round_amount_usd)}
                      </td>
                      <td className="num" data-label="Year">
                        {m.pattern.year ?? "n/a"}
                      </td>
                      <td className="num" data-label="Similarity">
                        <span className="sim" aria-hidden>
                          <span style={{ width: `${Math.round(m.similarity * 100)}%` }} />
                        </span>{" "}
                        {Math.round(m.similarity * 100)}%
                      </td>
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

      <details className="trace" open={printing}>
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

      <ConfirmDialog
        open={confirming}
        title="Delete this report?"
        body="The report is removed from this browser's list and from the server. This cannot be undone."
        confirmLabel="Delete report"
        onConfirm={onDelete}
        onCancel={() => setConfirming(false)}
      />
    </article>
  );
}
