import type { CartItem } from "../lib/cart-storage";
import { http } from "./http";

export type CheckoutPaymentMethod = "bank_transfer" | "mercadopago" | "cash";
const MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS = new Set([
  "www.mercadopago.com",
  "mercadopago.com",
  "www.mercadopago.com.ar",
  "mercadopago.com.ar",
  "sandbox.mercadopago.com",
  "www.sandbox.mercadopago.com"
]);

type GuestCustomer = {
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
};

type OrderData = {
  id: number;
  status: string;
  total_amount: number;
  items: Array<{ id: number }>;
};

type PaymentData = {
  id: number;
  method: "bank_transfer" | "mercadopago" | "cash";
  status: string;
  amount: number;
  currency: string;
  public_status_token?: string | null;
  provider_payload_data?: {
    checkout?: {
      checkout_url?: string | null;
      init_point?: string | null;
      sandbox_init_point?: string | null;
      public_status_token?: string | null;
    };
  };
};

type OrderEnvelope = {
  data: {
    id: number;
    status: string;
    total_amount: number;
    items: Array<{ id: number }>;
  };
  meta?: {
    created?: boolean;
  };
};

type GuestCheckoutEnvelope = {
  data: {
    order: OrderData;
    payment?: PaymentData;
  };
};

type CheckoutSubmitResult = {
  order: OrderData;
  payment: PaymentData | null;
};

export function getMercadoPagoCheckoutUrl(payment: PaymentData | null): string | null {
  if (!payment || payment.method !== "mercadopago") {
    return null;
  }
  const checkout = payment.provider_payload_data?.checkout;
  const checkoutUrl = checkout?.checkout_url?.trim();
  return checkoutUrl || null;
}

export function validateMercadoPagoCheckoutUrl(url: string): string {
  const normalizedUrl = url.trim();
  if (!normalizedUrl) {
    throw new Error("No se pudo obtener la URL de MercadoPago para continuar el pago.");
  }

  let parsed: URL;
  try {
    parsed = new URL(normalizedUrl);
  } catch {
    throw new Error("La URL de pago de MercadoPago es invalida.");
  }

  if (parsed.protocol !== "https:") {
    throw new Error("La URL de pago de MercadoPago debe usar HTTPS.");
  }

  const hostname = parsed.hostname.trim().toLowerCase().replace(/\.+$/, "");
  if (!MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS.has(hostname)) {
    throw new Error("La URL de pago de MercadoPago no pertenece a un dominio permitido.");
  }

  return parsed.toString();
}

export function redirectToMercadoPago(url: string): void {
  const safeUrl = validateMercadoPagoCheckoutUrl(url);
  window.location.assign(safeUrl);
}

function buildIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `guest_checkout_${crypto.randomUUID()}`;
  }
  return `guest_checkout_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function toCheckoutItems(items: CartItem[]) {
  return items.map((item) => ({
    variant_id: item.variant_id,
    quantity: item.quantity
  }));
}

export async function submitGuestCheckoutFromCart(
  items: CartItem[],
  customer: GuestCustomer,
  paymentMethod: CheckoutPaymentMethod
): Promise<CheckoutSubmitResult> {
  const payload = {
    customer,
    items: toCheckoutItems(items),
    website: "",
    payment_method: paymentMethod
  };
  const response = await http.post<GuestCheckoutEnvelope>("/checkout/guest", payload, {
    headers: {
      "Idempotency-Key": buildIdempotencyKey()
    }
  });
  return {
    order: response.data.data.order,
    payment: response.data.data.payment ?? null
  };
}

async function replaceDraftItems(items: CartItem[]): Promise<OrderEnvelope["data"]> {
  const response = await http.put<OrderEnvelope>("/orders/draft/items", {
    items: toCheckoutItems(items)
  });
  return response.data.data;
}

export async function submitAuthenticatedCheckoutFromCart(
  items: CartItem[],
  paymentMethod: CheckoutPaymentMethod
): Promise<CheckoutSubmitResult> {
  const draft = await replaceDraftItems(items);
  const orderId = draft.id;

  const submitted = await http.patch<OrderEnvelope>(`/orders/${orderId}/status`, {
    status: "submitted"
  });
  const paymentResponse = await http.post<{ data: PaymentData }>(
    `/orders/${orderId}/payments`,
    {
      method: paymentMethod,
      currency: "ARS",
      expires_in_minutes: 60
    },
    {
      headers: {
        "Idempotency-Key": `checkout_payment_${orderId}_${paymentMethod}_${buildIdempotencyKey()}`
      }
    }
  );
  return {
    order: submitted.data.data,
    payment: paymentResponse.data.data
  };
}
