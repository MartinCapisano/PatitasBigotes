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

export type MyPayment = {
  id: number;
  order_id: number;
  method: "bank_transfer" | "mercadopago" | "cash";
  status: "pending" | "paid" | "cancelled" | "expired";
  amount: number;
  currency: string;
  receipt_url: string | null;
  external_ref: string | null;
  created_at: string;
  paid_at: string | null;
};

export async function fetchPublicPaymentStatus(params: {
  publicStatusToken?: string | null;
}): Promise<PublicPaymentStatus> {
  const query = new URLSearchParams();
  if (params.publicStatusToken) query.set("public_status_token", params.publicStatusToken);
  const response = await http.get<PublicPaymentStatusEnvelope>(`/payments/public/status?${query.toString()}`);
  return response.data.data;
}

export async function listMyOrderPayments(orderId: number): Promise<MyPayment[]> {
  const response = await http.get<{ data: MyPayment[] }>(`/orders/${orderId}/payments`);
  return response.data.data;
}

export async function uploadBankTransferReceipt(orderId: number, paymentId: number, file: File): Promise<MyPayment> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await http.post<{ data: MyPayment }>(
    `/orders/${orderId}/payments/${paymentId}/bank-transfer/receipt`,
    formData
  );
  return response.data.data;
}
