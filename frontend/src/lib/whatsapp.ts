import type { CartItem } from "./cart-storage";
import { formatItemQuantity } from "./measure";
import { formatArs } from "./money";

const WHATSAPP_NUMBER = String(import.meta.env.VITE_WHATSAPP_NUMBER ?? "").trim();

/** Arma un enlace wa.me con el mensaje pre-cargado. Espeja el patrón del backend
 *  (`bank_transfer_s.build_whatsapp_receipt_url`). El número sale de
 *  `VITE_WHATSAPP_NUMBER`; sin número, abre WhatsApp para elegir contacto. */
export function buildWhatsappUrl(message: string, phoneNumber: string = WHATSAPP_NUMBER): string {
  const digits = phoneNumber.replace(/\D/g, "");
  const base = digits ? `https://wa.me/${digits}` : "https://wa.me/";
  return `${base}?text=${encodeURIComponent(message)}`;
}

export type AvailabilityCustomer = {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
};

/** Texto que el cliente manda al local para comprobar disponibilidad: la orden
 *  completa (ítems normales + por cantidad), total estimado y datos de contacto. */
export function buildAvailabilityMessage(items: CartItem[], customer?: AvailabilityCustomer): string {
  const lines: string[] = ["Hola! Quiero comprobar la disponibilidad de este pedido:", ""];

  let total = 0;
  for (const item of items) {
    const lineTotal = item.unit_price * item.quantity;
    total += lineTotal;
    const measureTag = item.sold_by === "measure" ? " (por cantidad)" : "";
    lines.push(`• ${item.product_name} — ${formatItemQuantity(item)}${measureTag} — ${formatArs(lineTotal)}`);
  }

  lines.push("", `Total estimado: ${formatArs(total)}`);

  const name = `${customer?.first_name ?? ""} ${customer?.last_name ?? ""}`.trim();
  const contactBits = [name, customer?.email?.trim() ?? "", customer?.phone?.trim() ?? ""].filter(Boolean);
  if (contactBits.length > 0) {
    lines.push("", `Mis datos: ${contactBits.join(" · ")}`);
  }

  return lines.join("\n");
}
