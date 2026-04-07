export type StorefrontProduct = {
  id: number;
  name: string;
  description: string | null;
  img_url: string | null;
  category_id: number;
  category_name: string | null;
  min_var_price: number | null;
  min_var_price_original?: number | null;
  min_var_price_final?: number | null;
  has_discount?: boolean;
  in_stock: boolean;
};

export type StorefrontOption = {
  variant_id: number;
  label: string;
  size: string | null;
  color: string | null;
  img_url: string | null;
  effective_img_url?: string | null;
  price: number;
  price_original?: number;
  price_final?: number;
  has_discount?: boolean;
  in_stock: boolean;
};

export type StorefrontProductDetail = StorefrontProduct & {
  option_axis: "size" | "color" | "variant";
  options: StorefrontOption[];
};

export type ApiEnvelope<T> = {
  data: T;
  meta?: Record<string, unknown>;
};

export type NotificationItem = {
  id: number;
  user_id: number | null;
  role_target: "admin" | null;
  event_type: string;
  title: string;
  message: string;
  order_id: number | null;
  payment_id: number | null;
  incident_id: number | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
};

export type LoginResponse = {
  logged_in: boolean;
  access_expires_in_seconds: number;
  access_expires_in_minutes: number;
};

export type MyProfile = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  has_account: boolean;
  is_admin: boolean;
  email_verified: boolean;
  email_verified_at: string | null;
  created_at: string;
};

export type MyOrderItem = {
  id: number;
  product_id: number;
  variant_id: number;
  product_name: string | null;
  variant_label: string;
  quantity: number;
  unit_price: number;
  line_total: number;
};

export type MyOrder = {
  id: number;
  status: "draft" | "submitted" | "paid" | "cancelled";
  currency: string;
  total_amount: number;
  created_at: string;
  items: MyOrderItem[];
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
