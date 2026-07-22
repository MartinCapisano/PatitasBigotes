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

/** What the customer needs in order to transfer. Built by the backend so the
 *  checkout screen, the email and "Mi cuenta" all say exactly the same thing. */
export type BankTransferInstructions = {
  alias: string;
  cbu: string;
  bank_name: string;
  holder: string;
  tax_id: string;
  reference: string;
  amount: number;
  currency: string;
  whatsapp_number: string;
  whatsapp_url: string;
};

export type MyPayment = {
  id: number;
  order_id: number;
  method: "bank_transfer" | "mercadopago" | "cash";
  status: "pending" | "paid" | "cancelled" | "expired";
  amount: number;
  currency: string;
  external_ref: string | null;
  preference_id?: string | null;
  public_status_token?: string | null;
  provider_status?: string | null;
  provider_payload_data?: {
    checkout?: {
      checkout_url?: string | null;
      init_point?: string | null;
      sandbox_init_point?: string | null;
      public_status_token?: string | null;
    };
    instructions?: Partial<BankTransferInstructions>;
  };
  created_at: string;
  paid_at: string | null;
};

export type PublicBankTransferItem = {
  product_name: string | null;
  variant_label: string;
  quantity: number;
  line_total: number;
};

export type PublicBankTransferStatus = {
  order_id: number;
  order_status: string;
  order_total: number;
  currency: string;
  items: PublicBankTransferItem[];
  payment_id: number;
  payment_status: string;
  can_pay: boolean;
  instructions: Partial<BankTransferInstructions> | null;
};

export type PublicOrderBlockingReason =
  | "order_paid"
  | "order_cancelled"
  | "payment_pending"
  | "payment_not_retryable"
  | "stock_reservation_expired"
  | "checkout_unavailable";

export type PublicOrderSnapshotItem = {
  product_name: string | null;
  variant_label: string;
  quantity: number;
  line_total: number;
};

export type PublicOrderSnapshotOrder = {
  status: "draft" | "submitted" | "paid" | "cancelled";
  total_amount: number;
  currency: string;
  items: PublicOrderSnapshotItem[];
};

export type PublicOrderSnapshotPayment = {
  method: "bank_transfer" | "mercadopago" | "cash";
  status: "pending" | "paid" | "cancelled" | "expired";
  amount: number;
  currency: string;
  checkout_url: string | null;
};

export type PublicOrderSnapshotFlags = {
  can_continue_payment: boolean;
  can_retry_payment: boolean;
  is_order_open: boolean;
  is_payment_terminal: boolean;
};

export type PublicOrderSnapshot = {
  order: PublicOrderSnapshotOrder;
  payment: PublicOrderSnapshotPayment;
  flags: PublicOrderSnapshotFlags;
  blocking_reason: PublicOrderBlockingReason | null;
};
