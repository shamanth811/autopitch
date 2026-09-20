import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, createJob, getApiKey, setApiKey } from "../api";
import { DeckPreview, keepDeck } from "../deckPreview";
import { useTitle } from "../useTitle";

const MAX_MB = 25;
const MAX_PAGES = 60;

/** Rough page count from the raw PDF. Compressed object streams hide pages, so 0 means unknown. */
async function estimatePages(f: File): Promise<number> {
  try {
    const text = await f.slice(0, 8 * 1024 * 1024).text();
    return (text.match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  } catch {
    return 0;
  }
}

function UploadIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden>
      <path d="M16 22V6m0 0-6 6m6-6 6 6M5 26h22" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function Analyze() {
  useTitle("Analyze a deck · AutoPitch");
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState(getApiKey);
  const [needsKey, setNeedsKey] = useState(() => getApiKey() !== "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function pick(f: File | undefined) {
    setError(null);
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      return setError("Only PDF decks are supported.");
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      return setError(`File is ${(f.size / 1048576).toFixed(1)} MB; the limit is ${MAX_MB} MB.`);
    }
    const pages = await estimatePages(f);
    if (pages > MAX_PAGES) {
      return setError(`This deck looks like ${pages} pages; the limit is ${MAX_PAGES}.`);
    }
    setFile(f);
  }

  async function submit() {
    if (!file) return;
    setApiKey(key);
    setBusy(true);
    setError(null);
    try {
      const { id } = await createJob(file);
      keepDeck(id, file);
      navigate(`/reports/${id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429 && e.retryAfter) {
        setError(`Rate limit reached. Try again in ${e.retryAfter}s.`);
      } else if (e instanceof ApiError && e.status === 401) {
        setNeedsKey(true);
        setError("This server needs an access key. Enter it below and try again.");
      } else {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
      setBusy(false);
    }
  }

  const choose = () => input.current?.click();

  return (
    <div className={`container${file ? " with-preview" : " narrow"}`}>
      <div className="main-col">
        <p className="eyebrow">New analysis</p>
        <h1>Upload your deck.</h1>
        <p className="lead">
          A PDF with selectable text, up to {MAX_MB} MB and {MAX_PAGES} pages. Analysis takes about
          a minute and keeps running if you leave this page.
        </p>

        <div
          className={`drop${drag ? " over" : ""}${file ? " has-file" : ""}`}
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
            <div
              className="drop-target"
              role="button"
              tabIndex={0}
              aria-label="Choose a PDF deck, or drop one here"
              onClick={choose}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  choose();
                }
              }}
            >
              <UploadIcon />
              <p>
                <strong>Drop a PDF here</strong>
                <span className="muted"> or press to browse</span>
              </p>
            </div>
          )}
          <div className="row">
            {file && (
              <button className="btn outline" onClick={choose} disabled={busy}>
                Choose a different file
              </button>
            )}
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

        {needsKey && (
          <label className="keyfield">
            <span className="eyebrow">Access key</span>
            <span className="muted">
              This server requires one. Kept for this browser session only.
            </span>
            <input
              type="password"
              autoComplete="off"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </label>
        )}

        <p className="muted note">
          The PDF is read in memory and not stored. Only the finished report is saved to this
          browser&apos;s report list.
        </p>
      </div>
      {file && (
        <aside className="side" aria-label="Deck preview">
          <DeckPreview file={file} />
        </aside>
      )}
    </div>
  );
}
