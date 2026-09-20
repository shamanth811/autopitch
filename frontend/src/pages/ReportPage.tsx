import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, deleteJob, getJob } from "../api";
import { ReportView } from "../ReportView";
import type { Job, Stage } from "../types";
import { useTitle } from "../useTitle";

const POLL_MS = 2000;

const STEPS: { stage: Stage; label: string }[] = [
  { stage: "extract", label: "Reading and extracting the deck" },
  { stage: "score", label: "Scoring six sections" },
  { stage: "benchmark", label: "Benchmarking against SEC filings" },
  { stage: "objections", label: "Drafting investor objections" },
];

function Progress({ job }: { job: Job }) {
  const current = STEPS.findIndex((s) => s.stage === job.stage);
  return (
    <>
      <p className="eyebrow">Analyzing</p>
      <h1>{job.filename}</h1>
      <p className="lead">This takes about a minute. You can leave this page; the report will be in My reports.</p>
      <ol className="steps" aria-live="polite">
        {STEPS.map((s, i) => (
          <li key={s.stage} className={i < current ? "done" : i === current ? "now" : ""}>
            {s.label}
          </li>
        ))}
      </ol>
    </>
  );
}

export function ReportPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  useTitle(job?.company ? `${job.company} · AutoPitch` : "Report · AutoPitch");

  useEffect(() => {
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;

    async function poll() {
      try {
        const j = await getJob(id, ctrl.signal);
        failures = 0;
        setError(null);
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        if (e instanceof ApiError && e.status === 404) return setMissing(true);
        // A dropped poll is not fatal: keep trying, but say so after a few in a row.
        failures += 1;
        if (failures >= 3) setError(e instanceof Error ? e.message : "Connection lost.");
        timer = setTimeout(poll, POLL_MS * 2);
      }
    }
    poll();
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [id]);

  async function remove() {
    await deleteJob(id);
    navigate("/reports");
  }

  if (missing) {
    return (
      <div className="container narrow">
        <p className="eyebrow">Not found</p>
        <h1>This report isn&apos;t here.</h1>
        <p className="lead">
          Reports are private to the browser that created them and are deleted after a retention
          period. Open this link in the browser you used to analyze the deck, or run the analysis
          again.
        </p>
        <Link to="/analyze" className="btn primary">
          Analyze a deck
        </Link>
      </div>
    );
  }

  return (
    <div className="container">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!job && !error && <p className="muted">Loading…</p>}
      {job && (job.status === "queued" || job.status === "running") && <Progress job={job} />}
      {job?.status === "failed" && (
        <div className="narrow">
          <p className="eyebrow">Analysis failed</p>
          <h1>{job.filename}</h1>
          <p className="error" role="alert">
            {job.error ?? "The analysis failed."}
          </p>
          <div className="row">
            <Link to="/analyze" className="btn primary">
              Try again
            </Link>
            <button className="btn outline" onClick={remove}>
              Remove
            </button>
          </div>
        </div>
      )}
      {job?.status === "done" && job.report && (
        <ReportView report={job.report} onDelete={remove} />
      )}
    </div>
  );
}
