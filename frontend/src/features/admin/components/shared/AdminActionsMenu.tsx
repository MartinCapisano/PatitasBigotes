import type { ReactNode } from "react";

export function AdminActionsMenu(props: {
  isOpen: boolean;
  onToggle: () => void;
  label: string;
  children: ReactNode;
}) {
  const { isOpen, onToggle, label, children } = props;

  return (
    <div className="admin-product-menu-wrap">
      <button
        className="btn btn-small btn-ghost"
        type="button"
        onClick={onToggle}
        aria-label={label}
      >
        ...
      </button>
      {isOpen ? <div className="admin-product-menu">{children}</div> : null}
    </div>
  );
}
