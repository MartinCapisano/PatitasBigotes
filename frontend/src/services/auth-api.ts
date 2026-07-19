import { http } from "./http";
import type { ApiEnvelope, LoginResponse, MyOrder, MyPayment, MyProfile } from "../types";

export async function login(email: string, password: string) {
  const response = await http.post<ApiEnvelope<LoginResponse>>("/auth/login", {
    email,
    password
  });
  return response.data.data;
}

export async function register(payload: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
}) {
  const response = await http.post<ApiEnvelope<{ registered: boolean }>>("/auth/register", payload);
  return response.data.data;
}

export async function requestPasswordReset(email: string) {
  const response = await http.post<ApiEnvelope<{ requested: boolean }>>("/auth/password/reset/request", {
    email
  });
  return response.data.data;
}

export async function confirmPasswordReset(token: string, newPassword: string) {
  const response = await http.post<ApiEnvelope<{ password_reset: boolean }>>("/auth/password/reset/confirm", {
    token,
    new_password: newPassword
  });
  return response.data.data;
}

export async function requestEmailVerification(email: string) {
  const response = await http.post<ApiEnvelope<{ requested: boolean }>>("/auth/email/verify/request", {
    email
  });
  return response.data.data;
}

export async function confirmEmailVerification(token: string) {
  const response = await http.post<ApiEnvelope<{ verified: boolean }>>("/auth/email/verify/confirm", {
    token
  });
  return response.data.data;
}

export async function logout() {
  const response = await http.post<ApiEnvelope<{ logged_out: boolean }>>("/auth/logout");
  return response.data.data;
}

export async function refreshSession() {
  const response = await http.post<
    ApiEnvelope<{
      refreshed: boolean;
      access_expires_in_seconds: number;
      access_expires_in_minutes: number;
    }>
  >("/auth/refresh");
  return response.data.data;
}

export async function getMyProfile() {
  const response = await http.get<ApiEnvelope<MyProfile>>("/auth/me");
  return response.data.data;
}

export async function updateMyProfile(payload: {
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
}) {
  const response = await http.patch<ApiEnvelope<MyProfile>>("/auth/me", payload);
  return {
    data: response.data.data,
    meta: response.data.meta ?? {}
  };
}

export async function getMyOrders(
  params?: { includePayments?: boolean }
): Promise<{ orders: MyOrder[]; paymentsByOrderId: Record<number, MyPayment[]> }> {
  if (!params?.includePayments) {
    const response = await http.get<ApiEnvelope<MyOrder[]>>("/orders");
    return { orders: response.data.data, paymentsByOrderId: {} };
  }
  const response = await http.get<
    ApiEnvelope<{ orders: MyOrder[]; payments_by_order_id: Record<number, MyPayment[]> }>
  >("/orders", { params: { include_payments: true } });
  return {
    orders: response.data.data.orders,
    paymentsByOrderId: response.data.data.payments_by_order_id
  };
}
