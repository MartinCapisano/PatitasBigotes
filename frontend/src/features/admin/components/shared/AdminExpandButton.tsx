export function AdminExpandButton(props: {
  expanded: boolean;
  onToggle: () => void;
  expandLabel: string;
  collapseLabel: string;
}) {
  const { expanded, onToggle, expandLabel, collapseLabel } = props;

  return (
    <button
      className="admin-expand-btn"
      type="button"
      onClick={onToggle}
      aria-label={expanded ? collapseLabel : expandLabel}
    >
      {expanded ? "v" : ">"}
    </button>
  );
}
