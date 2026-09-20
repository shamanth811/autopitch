import { Link } from "react-router-dom";
import { useTitle } from "../useTitle";

// Illustrative only: shows the shape of a report. Not a real company or a real result.
const EXAMPLE = [
  ["Problem", 6.7],
  ["Market", 6.0],
  ["Traction", 7.0],
  ["Team", 5.3],
  ["Moat", 6.5],
  ["Financials", 4.7],
] as const;

const STEPS = [
  {
    n: "01",
    title: "Upload your deck",
    body: "Drop in a PDF of up to 60 pages. The text of each slide is read; the file itself is never stored.",
  },
  {
    n: "02",
    title: "Structured extraction",
    body: "A model pulls out what the deck actually states: market size, ARR, growth, team, raise, runway. Missing data stays missing.",
  },
  {
    n: "03",
    title: "Six independent scorers",
    body: "Problem, market, traction, team, moat and financials are graded separately against a public rubric, so a strong team slide cannot hide a weak market.",
  },
  {
    n: "04",
    title: "Benchmark and objections",
    body: "Your raise is compared with funding rounds disclosed in SEC filings, then you get the questions an investor is most likely to ask.",
  },
];

const OUTPUTS = [
  {
    title: "A score you can audit",
    body: "Every criterion carries its score and the reasoning behind it. The composite is computed in code from stage-specific weights, never by the model.",
  },
  {
    title: "Comparable rounds",
    body: "See how the ask sits against real private financings from S-1 filings, with links back to the source documents.",
  },
  {
    title: "Investor objections",
    body: "Up to six likely questions, each tied to a specific gap in the deck, with the evidence to bring to the meeting.",
  },
];

const FAQ = [
  {
    q: "Is my deck stored?",
    a: "No. The PDF is read in memory and discarded. Only the finished report is saved, against an anonymous ID in your browser, and it is deleted after 30 days by default.",
  },
  {
    q: "Which models read my deck?",
    a: "The text of your slides is sent to the model providers the operator has configured to extract and score it. See the privacy page for the full list.",
  },
  {
    q: "Does it work on scanned or image-only decks?",
    a: "Yes, when OCR is enabled on this server. Pages with no selectable text are read with OCR, which can make the analysis a little slower. If OCR is switched off, an image-only deck is rejected and you should export it again with selectable text.",
  },
  {
    q: "Can I trust the score?",
    a: "Treat it as a screening aid. It reflects only what the deck states, is produced by language models, and is not investment advice. The methodology page shows exactly how it is calculated.",
  },
];

export function Landing() {
  useTitle("AutoPitch: score your pitch deck before the investor does");
  return (
    <>
      <section className="container hero-band">
        <div className="hero-grid">
          <div>
            <p className="eyebrow">Pitch deck analysis</p>
            <h1 className="hero-title">Score the deck before the investor does.</h1>
            <p className="lead">
              Upload a pitch deck and get a section-by-section score with the reasoning shown,
              a benchmark against funding rounds from SEC filings, and the objections you should
              be ready for.
            </p>
            <div className="row">
              <Link to="/analyze" className="btn primary">
                Analyze a deck
              </Link>
              <Link to="/methodology" className="btn outline">
                How it scores
              </Link>
            </div>
          </div>

          <aside className="example" aria-label="Example report layout">
            <p className="eyebrow">Example output</p>
            <p className="muted">Illustrative layout, not a real company.</p>
            <div className="composite">
              <span className="big">6.1</span>
              <span className="muted">/ 10 composite</span>
            </div>
            {EXAMPLE.map(([name, score]) => (
              <div className="ex-row" key={name}>
                <span>{name}</span>
                <span className="bar" aria-hidden>
                  <span style={{ width: `${score * 10}%` }} />
                </span>
                <span>{score.toFixed(1)}</span>
              </div>
            ))}
          </aside>
        </div>
      </section>

      <section className="container">
        <h2>How it works</h2>
        <ol className="steps-grid">
          {STEPS.map((s) => (
            <li key={s.n}>
              <p className="step-n">{s.n}</p>
              <h3>{s.title}</h3>
              <p className="serif">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="container">
        <h2>What you get</h2>
        <div className="cards">
          {OUTPUTS.map((o) => (
            <article key={o.title} className="card">
              <h3>{o.title}</h3>
              <p className="serif">{o.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="container">
        <h2>Questions</h2>
        <div className="faq">
          {FAQ.map((f) => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <p className="serif">{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="cta-band">
        <div className="container">
          <h2 className="on-dark">See where your deck is weak.</h2>
          <Link to="/analyze" className="btn inverse">
            Analyze a deck
          </Link>
        </div>
      </section>
    </>
  );
}
