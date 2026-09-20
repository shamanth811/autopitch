import { useEffect, useState } from "react";
import { getRubric } from "../api";
import { cap, pct, words } from "../format";
import type { Rubric } from "../types";
import { useTitle } from "../useTitle";

const STAGE_LABEL: Record<string, string> = {
  "pre-seed": "Pre-seed",
  seed: "Seed",
  "series-a": "Series A",
  other: "Other or unknown",
};

export function Methodology() {
  useTitle("Methodology · AutoPitch");
  const [rubric, setRubric] = useState<Rubric | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRubric()
      .then(setRubric)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the rubric."));
  }, []);

  return (
    <div className="container narrow prose">
      <p className="eyebrow">Methodology</p>
      <h1>How a deck is scored.</h1>
      <p className="lead">
        Language models read the deck and grade individual criteria. Everything after that, the
        section scores, the weights and the composite, is plain arithmetic in code.
      </p>

      <h2>The pipeline</h2>
      <ol className="serif plain-list">
        <li>
          <strong>Extract.</strong> The deck text becomes a structured record: market, traction,
          team, moat and financials. Anything the deck does not state stays empty.
        </li>
        <li>
          <strong>Score.</strong> Six scorers each see only their own section, so one strong slide
          cannot lift a weak one. They grade each criterion from 0 to 10 and cite the deck.
        </li>
        <li>
          <strong>Combine.</strong> A section&apos;s score is the mean of its criteria. The
          composite is the weighted mean of sections, with weights that depend on stage.
        </li>
        <li>
          <strong>Benchmark.</strong> Two optional layers. The raise is placed among thousands of
          real private raises from SEC Form D filings by young companies in the same sector, and
          similar companies from S-1 filings are shown when a close match exists. Form D has no
          funding stage, so that layer compares size only.
        </li>
        <li>
          <strong>Object.</strong> The model drafts likely investor questions, each grounded in a
          low score, a missing item or a benchmark finding.
        </li>
      </ol>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!rubric && !error && <p className="muted">Loading the rubric…</p>}

      {rubric && (
        <>
          <h2>Criteria</h2>
          {rubric.sections.map((s) => (
            <section key={s.name} className="rubric-section">
              <h3>{cap(s.name)}</h3>
              <dl>
                {s.criteria.map((c) => (
                  <div key={c.name}>
                    <dt>{cap(words(c.name))}</dt>
                    <dd className="serif">{c.description}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}

          <h2>Weights by stage</h2>
          <p className="serif">
            Earlier stages lean on team and problem because there is little revenue to judge.
            Later stages lean on traction and financials.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Section</th>
                  {Object.keys(rubric.weights_by_stage).map((st) => (
                    <th key={st} className="num">
                      {STAGE_LABEL[st] ?? cap(st)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rubric.sections.map((s) => (
                  <tr key={s.name}>
                    <td>{cap(s.name)}</td>
                    {Object.values(rubric.weights_by_stage).map((w, i) => (
                      <td key={i} className="num">
                        {w[s.name] === undefined ? "n/a" : pct(w[s.name]!)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Rules worth knowing</h2>
          <ul className="serif plain-list">
            <li>
              Missing data scores low. The scorers are told not to assume good news the deck did
              not state, and to list what is missing.
            </li>
            <li>
              A section scoring under {rubric.weak_threshold.toFixed(1)} is flagged as weak.
            </li>
            <li>
              If a section cannot be scored at all, it is excluded and the other weights are
              rescaled, so a failure never drags the composite toward zero. Exclusions are shown
              on the report.
            </li>
            <li>
              Deck text is treated as untrusted input. Instructions hidden inside a deck are
              ignored, and because scores are computed in code, a hijacked model can only fill
              typed fields, not change the weights.
            </li>
          </ul>
        </>
      )}

      <h2>Limits</h2>
      <p className="serif">
        The score reflects only what the deck states, judged by language models, so two runs can
        differ slightly. It does not verify claims, see images or charts that are not text, or
        know your market. It is a screening aid, not investment advice.
      </p>
    </div>
  );
}
