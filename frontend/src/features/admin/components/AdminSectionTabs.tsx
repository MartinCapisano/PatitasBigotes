import type { AdminSection } from "../types";

export function AdminSectionTabs(props: {
  adminSection: AdminSection;
  sections: AdminSection[];
  onSelect: (section: AdminSection) => void;
}) {
  const { adminSection, sections, onSelect } = props;
  return (
    <div className="admin-section-tabs">
      {sections.map((section) => (
        <button
          key={section}
          className={`btn btn-small ${adminSection === section ? "" : "btn-ghost"}`}
          type="button"
          onClick={() => onSelect(section)}
        >
          {section === "categorias"
            ? "Categorias"
            : section === "catalogo"
            ? "Catalogo"
            : section === "descuentos"
            ? "Descuentos"
            : section === "turnos"
            ? "Turnos"
            : section === "ordenes"
            ? "Ordenes"
            : section === "pagos"
            ? "Pagos"
            : section === "incidencias_pago"
            ? "Incidencias"
            : section === "registrar_venta"
            ? "Registrar venta"
            : section === "transferencias"
            ? "Transferencias"
            : "Registrar pago"}
        </button>
      ))}
    </div>
  );
}
