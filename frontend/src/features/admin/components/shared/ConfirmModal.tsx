import { useModalA11y } from "../../../../lib/useModalA11y";

type ConfirmModalProps = {
  title: string;
  message: string;
  confirmLabel?: string;
  busyLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmModal({
  title,
  message,
  confirmLabel = "Confirmar",
  busyLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel
}: ConfirmModalProps) {
  const modalRef = useModalA11y<HTMLDivElement>(true, onCancel);

  return (
    <div
      ref={modalRef}
      className="admin-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabIndex={-1}
    >
      <div className="card admin-modal admin-modal-confirm">
        <div className="admin-modal-header">
          <h3>{title}</h3>
          <button
            className="btn btn-small btn-ghost"
            type="button"
            onClick={onCancel}
            disabled={busy}
          >
            Cancelar
          </button>
        </div>
        <p>{message}</p>
        <div className="admin-product-actions">
          <button
            className={`btn btn-small${danger ? " btn-danger" : ""}`}
            type="button"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy && busyLabel ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
