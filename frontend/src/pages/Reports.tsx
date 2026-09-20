import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteJob, listJobs } from "../api";
import { ConfirmDialog } from "../ConfirmDialog";
import { tone, when } from "../format";
import type { JobSummary } from "../types";
import { useTitle } from "../useTitle";

const STAGE: Record<string, string> = {
  queued: "Queued",
  extract: "Reading deck",
  score: "Scoring",
  benchmark: "Benchmarking",
  objections: "Objections",
};

type Sort = "newest" | "score" | "company";

function Status({ j }: { j: JobSummary }) {
  if (j.status === "done") return <span>Ready</span>;
  if (j.status === "failed") return <span className="tag weak">Failed</span>;
  return (
    <span className="running">
      <span className="dot" aria-hidden /> {STAGE[j.stage] ?? "Analyzing"}
    </span>
  );
}

export function Reports() {
  useTitle("My reports · AutoPitch");
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<JobSummary | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("newest");

  const load = useCallback(async () => {
    try {
      setJobs(await listJobs());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load reports.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Keep refreshing while anything is still running.
  const active = jobs?.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [active, load]);

  async function remove(id: string) {
    setConfirming(null);
    await deleteJob(id);
    load();
  }

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (jobs ?? []).filter(
      (j) => !q || `${j.company ?? ""} ${j.filename}`.toLowerCase().includes(q),
    );
    const by: Record<Sort, (a: JobSummary, b: JobSummary) => number> = {
      newest: (a, b) => b.created_at.localeCompare(a.created_at),
      score: (a, b) => (b.score ?? -1) - (a.score ?? -1),
      company: (a, b) => (a.company ?? "~").localeCompare(b.company ?? "~"),
    };
    return list.sort(by[sort]);
  }, [jobs, query, sort]);

  return (
    <div className="container">
      <p className="eyebrow">History</p>
      <h1>My reports</h1>
      <p className="lead">
        Saved in this browser&apos;s anonymous session and deleted after 30 days by default. They
        are not tied to an account, so clearing your browser data removes access to them.
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!jobs && !error && (
        <div className="skeleton" aria-busy="true" aria-label="Loading reports">
          <span className="sk sk-line" />
          <span className="sk sk-line" />
          <span className="sk sk-line short" />
        </div>
      )}

      {jobs && jobs.length === 0 && (
        <div className="empty">
          <p className="serif">No reports yet.</p>
          <Link to="/analyze" className="btn primary">
            Analyze your first deck
          </Link>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <>
          <div className="toolbar">
            <label className="field">
              <span className="visually-hidden">Search reports</span>
              <input
                type="search"
                placeholder="Search company or file"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="muted">Sort by</span>
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
                <option value="newest">Newest</option>
                <option value="score">Highest score</option>
                <option value="company">Company A to Z</option>
              </select>
            </label>
          </div>

          {shown.length === 0 ? (
            <p className="muted">No reports match &ldquo;{query}&rdquo;.</p>
          ) : (
            <div className="table-wrap">
              <table className="stack">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>File</th>
                    <th>Status</th>
                    <th>Score</th>
                    <th>Created</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <Link to={`/reports/${j.id}`}>{j.company ?? "Untitled deck"}</Link>
                      </td>
                      <td className="wrap" data-label="File">
                        {j.filename}
                      </td>
                      <td data-label="Status">
                        <Status j={j} />
                      </td>
                      <td data-label="Score">
                        {j.score === null ? (
                          "n/a"
                        ) : (
                          <span className="score-cell">
                            <span className="bar" aria-hidden>
                              <span
                                className={tone(j.score)}
                                style={{ width: `${j.score * 10}%` }}
                              />
                            </span>
                            {j.score.toFixed(1)}
                          </span>
                        )}
                      </td>
                      <td data-label="Created">{when(j.created_at)}</td>
                      <td className="num">
                        <button className="link-btn" onClick={() => setConfirming(j)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirming !== null}
        title="Delete this report?"
        body={`${confirming?.company ?? confirming?.filename ?? "This report"} will be removed. This cannot be undone.`}
        confirmLabel="Delete report"
        onConfirm={() => confirming && remove(confirming.id)}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}
