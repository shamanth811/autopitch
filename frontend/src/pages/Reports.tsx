import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteJob, listJobs } from "../api";
import { when } from "../format";
import type { JobSummary } from "../types";
import { useTitle } from "../useTitle";

const STATUS: Record<JobSummary["status"], string> = {
  queued: "Queued",
  running: "Analyzing",
  done: "Ready",
  failed: "Failed",
};

export function Reports() {
  useTitle("My reports · AutoPitch");
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

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
    await deleteJob(id);
    setConfirming(null);
    load();
  }

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
      {!jobs && !error && <p className="muted">Loading…</p>}

      {jobs && jobs.length === 0 && (
        <div className="empty">
          <p className="serif">No reports yet.</p>
          <Link to="/analyze" className="btn primary">
            Analyze your first deck
          </Link>
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>File</th>
                <th>Status</th>
                <th className="num">Score</th>
                <th>Created</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link to={`/reports/${j.id}`}>{j.company ?? "Untitled deck"}</Link>
                  </td>
                  <td className="wrap">{j.filename}</td>
                  <td>{STATUS[j.status]}</td>
                  <td className="num">{j.score === null ? "n/a" : j.score.toFixed(1)}</td>
                  <td>{when(j.created_at)}</td>
                  <td className="num">
                    {confirming === j.id ? (
                      <>
                        <button className="link-btn danger" onClick={() => remove(j.id)}>
                          Confirm delete
                        </button>{" "}
                        <button className="link-btn" onClick={() => setConfirming(null)}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button className="link-btn" onClick={() => setConfirming(j.id)}>
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
