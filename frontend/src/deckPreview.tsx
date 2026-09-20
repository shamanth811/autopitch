import { useEffect, useState } from "react";

// The server never stores the PDF, so the only copy is the File the user picked. Keep it in
// memory (not localStorage) for the life of this tab so the report page can show it beside the
// results. A reload drops it; the report itself is unaffected.
const kept = new Map<string, File>();

export function keepDeck(jobId: string, file: File): void {
  kept.set(jobId, file);
}

export function forgetDeck(jobId: string): void {
  kept.delete(jobId);
}

export function getDeck(jobId: string): File | undefined {
  return kept.get(jobId);
}

/** Object URL for a file, revoked when the file changes or the component unmounts. */
function useObjectUrl(file: File): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  return url;
}

export function DeckPreview({ file }: { file: File }) {
  const url = useObjectUrl(file);
  if (!url) return null;
  return (
    <figure className="preview">
      <figcaption>
        <span className="eyebrow">Your deck</span>
        <a href={url} target="_blank" rel="noopener noreferrer" className="preview-open">
          Open full size
        </a>
      </figcaption>
      <iframe
        src={`${url}#toolbar=0&navpanes=0&view=FitH`}
        title={`Preview of ${file.name}`}
        className="preview-frame"
      />
      <p className="muted preview-note">
        Shown from your browser only. Reloading this page clears it.
      </p>
    </figure>
  );
}
