import { http } from "./http";

export type PublicPaymentStatus = {
  order_status: string | null;
  status: "pending" | "paid" | "cancelled" | "expired";
  updated_at: string | null;
  paid_at: string | null;
};

type PublicPaymentStatusEnvelope = {
  data: PublicPaymentStatus;
};

export async function fetchPublicPaymentStatus(params: {
  publicStatusToken?: string | null;
}): Promise<PublicPaymentStatus> {
  const query = new URLSearchParams();
  if (params.publicStatusToken) query.set("public_status_token", params.publicStatusToken);
  const response = await http.get<PublicPaymentStatusEnvelope>(`/payments/public/status?${query.toString()}`);
  return response.data.data;
}
