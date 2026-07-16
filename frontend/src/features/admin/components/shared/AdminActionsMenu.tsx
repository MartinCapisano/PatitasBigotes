import { useRef, type ReactNode } from "react";
import { useClickOutside } from "../../../../lib/useClickOutside";

export function AdminActionsMenu(props: {
  isOpen: boolean;
  onToggle: () => void;
  label: string;
  children: ReactNode;
}) {
  const { isOpen, onToggle, label, children } = props;
  const wrapRef = useRef<HTMLDivElement>(null);
  useClickOutside(wrapRef, isOpen, onToggle);

  return (
    <div className="admin-product-menu-wrap" ref={wrapRef}>
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
