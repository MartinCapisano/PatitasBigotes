import type { CheckoutPaymentMethod } from "../../../services/checkout-api";

export type PaymentMethodOption = {
  value: CheckoutPaymentMethod;
  label: string;
};

const TRUTHY = new Set(["1", "true", "yes", "on"]);

/**
 * Mirrors the backend `MERCADOPAGO_ENABLED` flag, with the same safe default:
 * disabled unless explicitly turned on. Hiding the option here is a courtesy to
 * the customer, not the lock -- the server rejects the method regardless.
 */
export function isMercadoPagoEnabled(): boolean {
  const raw = String(import.meta.env.VITE_MERCADOPAGO_ENABLED ?? "")
    .trim()
    .toLowerCase();
  return TRUTHY.has(raw);
}

export function getAvailablePaymentMethods(): PaymentMethodOption[] {
  const options: PaymentMethodOption[] = [
    { value: "bank_transfer", label: "Transferencia" }
  ];
  if (isMercadoPagoEnabled()) {
    options.push({ value: "mercadopago", label: "MercadoPago" });
  }
  options.push({ value: "cash", label: "Efectivo" });
  return options;
}
