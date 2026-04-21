import { http } from "./http";
import type { MyPayment, PublicOrderSnapshot } from "../types";

export type PublicPaymentStatus = {
  order_status: string | null;
  status: "pending" | "paid" | "cancelled" | "expired";
  updated_at: string | null;
  paid_at: string | null;
};

type PublicPaymentStatusEnvelope = {
  data: PublicPaymentStatus;
};

type PublicOrderSnapshotEnvelope = {
  data: PublicOrderSnapshot;
};

export async function fetchPublicPaymentStatus(params: {
  publicStatusToken?: string | null;
}): Promise<PublicPaymentStatus> {
  const query = new URLSearchParams();
  if (params.publicStatusToken) query.set("public_status_token", params.publicStatusToken);
  const response = await http.get<PublicPaymentStatusEnvelope>(`/payments/public/status?${query.toString()}`);
  return response.data.data;
}

export async function fetchPublicOrderSnapshotByPaymentToken(params: {
  publicStatusToken?: string | null;
}): Promise<PublicOrderSnapshot> {
  const query = new URLSearchParams();
  if (params.publicStatusToken) query.set("public_status_token", params.publicStatusToken);
  const response = await http.get<PublicOrderSnapshotEnvelope>(`/public/orders/by-payment-token?${query.toString()}`);
  return response.data.data;
}

export async function retryGuestMercadoPago(publicStatusToken: string): Promise<MyPayment> {
  const response = await http.post<{ data: MyPayment }>(
    `/payments/${encodeURIComponent(publicStatusToken)}/retry`
  );
  return response.data.data;
}

export async function listMyOrderPayments(orderId: number): Promise<MyPayment[]> {
  const response = await http.get<{ data: MyPayment[] }>(`/orders/${orderId}/payments`);
  return response.data.data;
}

export async function retryMyOrderMercadoPago(orderId: number): Promise<MyPayment> {
  const response = await http.post<{ data: MyPayment }>(`/orders/${orderId}/payments/retry`, {
    method: "mercadopago",
    currency: "ARS",
    expires_in_minutes: 60
  });
  return response.data.data;
}
