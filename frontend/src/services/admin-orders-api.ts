import { http } from "./http";

export type ManualOrderItem = {
  variant_id: number;
  quantity: number;
};

export type AdminOrderItem = {
  id: number;
  product_id: number;
  variant_id: number;
  product_name: string | null;
  variant_label: string;
  quantity: number;
  unit_price: number;
  line_total: number;
};

export type AdminOrder = {
  id: number;
  user_id: number;
  customer: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    phone: string | null;
  } | null;
  status: "draft" | "submitted" | "paid" | "cancelled";
  currency: "ARS";
  total_amount: number;
  subtotal: number;
  discount_total: number;
  items: AdminOrderItem[];
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  paid_at: string | null;
};

export type AdminPayment = {
  id: number;
  order_id: number;
  method: "bank_transfer" | "mercadopago" | "cash";
  status: "pending" | "paid" | "cancelled" | "expired";
  amount: number;
  change_amount?: number | null;
  currency: "ARS";
  external_ref: string | null;
  public_status_token?: string | null;
  receipt_url: string | null;
  preference_id: string | null;
  order_status?: "draft" | "submitted" | "paid" | "cancelled" | null;
  user_id?: number | null;
  has_open_incident?: boolean;
  incident_status?: "pending_review" | "resolved_refunded" | "resolved_no_refund" | null;
  created_at: string;
  paid_at: string | null;
};

export type AdminPaymentIncident = {
  id: number;
  order_id: number;
  payment_id: number;
  type: "late_paid_duplicate";
  status: "pending_review" | "resolved_refunded" | "resolved_no_refund";
  reason: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by_user_id: number | null;
  payment: {
    id: number | null;
    method: "bank_transfer" | "mercadopago" | "cash" | null;
    status: "pending" | "paid" | "cancelled" | "expired" | null;
    amount: number | null;
    currency: "ARS" | null;
    external_ref: string | null;
  };
  order: {
    id: number | null;
    status: "draft" | "submitted" | "paid" | "cancelled" | null;
    total_amount: number | null;
    user_id: number | null;
  };
};

export async function getAdminOrder(orderId: number): Promise<AdminOrder> {
  const response = await http.get<{ data: AdminOrder }>(`/admin/orders/${orderId}`);
  return response.data.data;
}

export async function listAdminOrderPayments(orderId: number): Promise<AdminPayment[]> {
  const response = await http.get<{ data: AdminPayment[] }>(`/admin/orders/${orderId}/payments`);
  return response.data.data;
}

export async function listAdminOrders(params?: {
  status?: "draft" | "submitted" | "paid" | "cancelled";
  limit?: number;
  sort_by?: "created_at" | "id";
  sort_dir?: "asc" | "desc";
}): Promise<AdminOrder[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.sort_by) qs.set("sort_by", params.sort_by);
  if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
  const response = await http.get<{ data: AdminOrder[] }>(`/admin/orders?${qs.toString()}`);
  return response.data.data;
}

export async function listAdminPayments(params?: {
  status?: "pending" | "paid" | "cancelled" | "expired";
  limit?: number;
  sort_by?: "created_at" | "id";
  sort_dir?: "asc" | "desc";
}): Promise<AdminPayment[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.sort_by) qs.set("sort_by", params.sort_by);
  if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
  const response = await http.get<{ data: AdminPayment[] }>(`/admin/payments?${qs.toString()}`);
  return response.data.data;
}

export async function listAdminPaymentIncidents(params?: {
  status?: "pending_review" | "resolved_refunded" | "resolved_no_refund";
  limit?: number;
}): Promise<AdminPaymentIncident[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  const response = await http.get<{ data: AdminPaymentIncident[] }>(`/admin/payment-incidents?${qs.toString()}`);
  return response.data.data;
}

export async function resolveAdminPaymentIncidentRefund(payload: {
  incident_id: number;
  amount?: number;
  reason: string;
}): Promise<{ incident: AdminPaymentIncident; refund: { id: number; status: string; provider_refund_id: string | null } }> {
  const response = await http.post<{
    data: { incident: AdminPaymentIncident; refund: { id: number; status: string; provider_refund_id: string | null } };
  }>(`/admin/payment-incidents/${payload.incident_id}/resolve-refund`, {
    amount: payload.amount,
    reason: payload.reason
  });
  return response.data.data;
}

export async function resolveAdminPaymentIncidentNoRefund(payload: {
  incident_id: number;
  reason: string;
}): Promise<AdminPaymentIncident> {
  const response = await http.post<{ data: AdminPaymentIncident }>(
    `/admin/payment-incidents/${payload.incident_id}/resolve-no-refund`,
    {
      reason: payload.reason
    }
  );
  return response.data.data;
}

export async function registerAdminOrderManualPayment(payload: {
  order_id: number;
  method: "cash" | "bank_transfer";
  paid_amount: number;
  change_amount?: number;
  payment_ref?: string;
}): Promise<{ order: AdminOrder; payment: AdminPayment }> {
  const response = await http.post<{ data: { order: AdminOrder; payment: AdminPayment } }>(
    `/admin/orders/${payload.order_id}/payments/manual`,
    {
      method: payload.method,
      paid_amount: payload.paid_amount,
      change_amount: payload.change_amount,
      payment_ref: payload.payment_ref
    }
  );
  return response.data.data;
}
