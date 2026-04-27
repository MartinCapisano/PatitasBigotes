import { http } from "./http";
import type { ApiEnvelope, StorefrontProduct, StorefrontProductDetail } from "../types";

export async function fetchStorefrontProducts(params?: {
  q?: string;
  category_id?: number;
  min_price?: number;
  max_price?: number;
  sort_by?: "price" | "name";
  sort_order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}) {
  const response = await http.get<ApiEnvelope<StorefrontProduct[]>>("/storefront/products", {
    params
  });
  return response.data;
}

export async function fetchStorefrontProductById(productId: number) {
  const response = await http.get<ApiEnvelope<StorefrontProductDetail>>(
    `/storefront/products/${productId}`
  );
  return response.data;
}

export async function fetchStorefrontCategories() {
  const response = await http.get<ApiEnvelope<Array<{ id: number; name: string }>>>(
    "/storefront/categories"
  );
  return response.data;
}
