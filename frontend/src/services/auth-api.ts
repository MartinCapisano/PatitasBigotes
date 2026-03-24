import { http } from "./http";
import type { ApiEnvelope, LoginResponse, MyOrder, MyProfile } from "../types";

export async function login(email: string, password: string) {
  const response = await http.post<ApiEnvelope<LoginResponse>>("/auth/login", {
    email,
    password
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

export async function getMyOrders() {
  const response = await http.get<ApiEnvelope<MyOrder[]>>("/orders");
  return response.data.data;
}
