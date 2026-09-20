import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, createJob, getApiKey, setApiKey } from "../api";
import { useTitle } from "../useTitle";

const MAX_MB = 25;

export function Analyze() {
  useTitle("Analyze a deck · AutoPitch");
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState(getApiKey);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function pick(f: File | undefined) {
    setError(null);
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      return setError("Only PDF decks are supported.");
    }
    if (f.size > MAX_MB * 1024 * 1024) return setError(`File exceeds ${MAX_MB} MB.`);
    setFile(f);
  }

  async function submit() {
    if (!file) return;
    setApiKey(key);
    setBusy(true);
    setError(null);
    try {
      const { id } = await createJob(file);
      navigate(`/reports/${id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429 && e.retryAfter) {
        setError(`Rate limit reached. Try again in ${e.retryAfter}s.`);
      } else {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
      setBusy(false);
    }
  }

  return (
    <div className="container narrow">
      <p className="eyebrow">New analysis</p>
      <h1>Upload your deck.</h1>
      <p className="lead">
        A PDF with selectable text, up to {MAX_MB} MB and 60 pages. Analysis takes about a minute
        and keeps running if you leave this page.
      </p>

      <div
        className={`drop${drag ? " over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          pick(e.dataTransfer.files[0]);
        }}
      >
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => pick(e.target.files?.[0])}
        />
        {file ? (
          <p className="filename">
            {file.name} <span className="muted">({(file.size / 1048576).toFixed(1)} MB)</span>
          </p>
        ) : (
          <p className="muted">Drop a PDF here, or choose a file.</p>
        )}
        <div className="row">
          <button className="btn outline" onClick={() => input.current?.click()} disabled={busy}>
            {file ? "Choose a different file" : "Choose file"}
          </button>
          <button className="btn primary" onClick={submit} disabled={!file || busy}>
            {busy ? "Uploading…" : "Analyze deck"}
          </button>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <details className="advanced">
        <summary>Access key</summary>
        <label>
          <span className="muted">
            Only needed if this server requires one. Kept for this browser session only.
          </span>
          <input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
      </details>

      <p className="muted note">
        The PDF is read in memory and not stored. Only the finished report is saved to this
        browser&apos;s report list.
      </p>
    </div>
  );
}
