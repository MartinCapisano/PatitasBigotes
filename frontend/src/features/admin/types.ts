export type AdminSection =
  | "categorias"
  | "catalogo"
  | "descuentos"
  | "turnos"
  | "ordenes"
  | "pagos"
  | "incidencias_pago"
  | "registrar_venta"
  | "registrar_pago"
  | "transferencias";

export type AdminMode = "ver" | "venta";

export const ADMIN_VIEW_SECTIONS: AdminSection[] = [
  "categorias",
  "catalogo",
  "descuentos",
  "turnos",
  "ordenes",
  "pagos"
];

export const ADMIN_SALES_SECTIONS: AdminSection[] = [
  "registrar_venta",
  "registrar_pago",
  "transferencias",
  "incidencias_pago"
];

