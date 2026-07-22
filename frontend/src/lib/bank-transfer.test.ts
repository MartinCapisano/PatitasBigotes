import { describe, expect, it } from "vitest";
import { getBankTransferInstructions } from "./bank-transfer";
import type { BankTransferInstructions } from "../types";

const INSTRUCTIONS: BankTransferInstructions = {
  alias: "patitas.bigotes.real",
  cbu: "0110599520000012345678",
  bank_name: "Banco Nacion",
  holder: "Martin Capisano",
  tax_id: "20-35123456-7",
  reference: "ORDER-12-PAY-34",
  amount: 250000,
  currency: "ARS",
  whatsapp_number: "5493511234567",
  whatsapp_url: "https://wa.me/5493511234567?text=Referencia%3A%20ORDER-12-PAY-34"
};

function payment(overrides: Record<string, unknown> = {}) {
  return {
    id: 34,
    method: "bank_transfer" as const,
    status: "pending",
    amount: 250000,
    currency: "ARS",
    provider_payload_data: { instructions: INSTRUCTIONS },
    ...overrides
  };
}

describe("getBankTransferInstructions", () => {
  it("returns the instructions of a bank transfer payment", () => {
    expect(getBankTransferInstructions(payment())).toEqual(INSTRUCTIONS);
  });

  it("returns nothing when there is no payment", () => {
    expect(getBankTransferInstructions(null)).toBeNull();
  });

  it("ignores payments of other methods", () => {
    expect(
      getBankTransferInstructions(payment({ method: "cash", provider_payload_data: undefined }))
    ).toBeNull();
    expect(
      getBankTransferInstructions(
        payment({
          method: "mercadopago",
          provider_payload_data: { checkout: { checkout_url: "https://mp.test" } }
        })
      )
    ).toBeNull();
  });

  it("returns nothing when the payload carries no instructions", () => {
    expect(getBankTransferInstructions(payment({ provider_payload_data: {} }))).toBeNull();
  });

  it.each([
    "alias",
    "cbu",
    "bank_name",
    "holder",
    "tax_id",
    "reference",
    "whatsapp_url"
  ] as const)("refuses to render when %s is missing", (field) => {
    const partial = { ...INSTRUCTIONS };
    delete partial[field];

    expect(
      getBankTransferInstructions(payment({ provider_payload_data: { instructions: partial } }))
    ).toBeNull();
  });

  it("treats a blank value as missing", () => {
    expect(
      getBankTransferInstructions(
        payment({ provider_payload_data: { instructions: { ...INSTRUCTIONS, cbu: "   " } } })
      )
    ).toBeNull();
  });

  it("refuses to render without an amount to transfer", () => {
    const withoutAmount: Partial<BankTransferInstructions> = { ...INSTRUCTIONS };
    delete withoutAmount.amount;

    expect(
      getBankTransferInstructions(
        payment({ provider_payload_data: { instructions: withoutAmount } })
      )
    ).toBeNull();
  });
});
