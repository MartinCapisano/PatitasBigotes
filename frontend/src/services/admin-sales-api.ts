import { http } from "./http";
import type { ManualOrderItem } from "./admin-orders-api";
import type { components } from "../types/api.generated";

export type AdminSearchUser = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  dni: string | null;
  phone: string | null;
  has_account: boolean;
};

export type AdminSalesCustomerPayload =
  | {
      mode: "existing";
      user_id: number;
    }
  | {
      mode: "new";
      first_name: string;
      last_name: string;
      email: string;
      phone: string;
      dni?: string | null;
    };

export type AdminSalesPaymentPayload = {
  method: "cash" | "bank_transfer";
  amount_paid: number;
  change_amount?: number | null;
  payment_ref?: string | null;
};

export type CreateAdminSalePayload = {
  customer: AdminSalesCustomerPayload;
  items: ManualOrderItem[];
  register_payment: boolean;
  payment?: AdminSalesPaymentPayload | null;
};

// RM-1: la forma de la respuesta la fija el backend (response_model en
// POST /admin/sales). Consumimos el tipo generado desde el OpenAPI en vez de
// mantener una copia a mano que podía driftear en silencio.
export type CreateAdminSaleResponse = components["schemas"]["CreateAdminSaleResponse"];

export async function searchAdminUsers(params: {
  email?: string;
  dni?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  limit?: number;
}): Promise<AdminSearchUser[]> {
  const response = await http.get<{ data: AdminSearchUser[] }>("/users/search", {
    params
  });
  return response.data.data;
}

export async function createAdminSale(payload: CreateAdminSalePayload): Promise<CreateAdminSaleResponse> {
  const response = await http.post<{ data: CreateAdminSaleResponse }>("/admin/sales", payload);
  return response.data.data;
}
