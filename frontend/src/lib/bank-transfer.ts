import type { BankTransferInstructions } from "../types";

const REQUIRED_FIELDS = [
  "alias",
  "cbu",
  "bank_name",
  "holder",
  "tax_id",
  "reference",
  "whatsapp_url"
] as const;

/**
 * Returns the instructions only when every field the customer needs is there.
 *
 * A half-rendered screen is worse than no screen: someone reading a blank alias
 * or a missing reference can still send the money, and then nobody can match it
 * to an order. Callers fall back to a plain status message instead.
 *
 * Shared because the same instructions are shown in three places -- right after
 * checkout, from "Mi cuenta", and from the guest's public link -- and they all
 * have to apply the same bar.
 */
export function readBankTransferInstructions(
  instructions: Partial<BankTransferInstructions> | null | undefined
): BankTransferInstructions | null {
  if (!instructions) {
    return null;
  }
  const hasEveryField = REQUIRED_FIELDS.every(
    (field) => typeof instructions[field] === "string" && instructions[field]!.trim() !== ""
  );
  if (!hasEveryField || typeof instructions.amount !== "number") {
    return null;
  }
  return instructions as BankTransferInstructions;
}

type PaymentLike = {
  method: string;
  provider_payload_data?: {
    instructions?: Partial<BankTransferInstructions>;
  } | null;
} | null;

/** The same rule, applied to a payment as the API returns it. */
export function getBankTransferInstructions(payment: PaymentLike): BankTransferInstructions | null {
  if (!payment || payment.method !== "bank_transfer") {
    return null;
  }
  return readBankTransferInstructions(payment.provider_payload_data?.instructions);
}

/** The public route that reopens these instructions without a login. */
export function buildBankTransferStatusUrl(token: string, origin: string): string {
  return `${origin}/transferencia?token=${encodeURIComponent(token)}`;
}

/** Whether this payment is still waiting for the customer's transfer. */
export function isAwaitingTransfer(
  payment: { method: string; status: string } | null,
  orderStatus: string
): boolean {
  if (!payment) return false;
  return (
    payment.method === "bank_transfer" &&
    payment.status === "pending" &&
    orderStatus === "submitted"
  );
}
