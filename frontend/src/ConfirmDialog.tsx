import { useEffect, useRef } from "react";

/** Modal confirmation on a native <dialog>: focus trap, Esc to cancel, backdrop. */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="dialog" onCancel={onCancel} onClose={onCancel}>
      <h3>{title}</h3>
      <p className="serif">{body}</p>
      <div className="row">
        <button className="btn outline" onClick={onCancel} autoFocus>
          Cancel
        </button>
        <button className="btn primary" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
