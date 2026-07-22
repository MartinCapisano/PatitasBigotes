import { afterEach, describe, expect, it, vi } from "vitest";
import { getAvailablePaymentMethods, isMercadoPagoEnabled } from "./payment-methods";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isMercadoPagoEnabled", () => {
  it("defaults to disabled when the flag is not set", () => {
    vi.stubEnv("VITE_MERCADOPAGO_ENABLED", "");

    expect(isMercadoPagoEnabled()).toBe(false);
  });

  it("accepts the same truthy spellings as the backend flag", () => {
    for (const raw of ["1", "true", "TRUE", " yes ", "on"]) {
      vi.stubEnv("VITE_MERCADOPAGO_ENABLED", raw);
      expect(isMercadoPagoEnabled()).toBe(true);
    }
  });

  it("treats anything else as disabled", () => {
    for (const raw of ["0", "false", "no", "off", "tru"]) {
      vi.stubEnv("VITE_MERCADOPAGO_ENABLED", raw);
      expect(isMercadoPagoEnabled()).toBe(false);
    }
  });
});

describe("getAvailablePaymentMethods", () => {
  it("offers only transferencia and efectivo while MercadoPago is paused", () => {
    vi.stubEnv("VITE_MERCADOPAGO_ENABLED", "false");

    expect(getAvailablePaymentMethods().map((method) => method.value)).toEqual([
      "bank_transfer",
      "cash"
    ]);
  });

  it("puts MercadoPago back between them when it is reactivated", () => {
    vi.stubEnv("VITE_MERCADOPAGO_ENABLED", "true");

    expect(getAvailablePaymentMethods().map((method) => method.value)).toEqual([
      "bank_transfer",
      "mercadopago",
      "cash"
    ]);
  });

  it("always leaves transferencia first, so it is the default selection", () => {
    vi.stubEnv("VITE_MERCADOPAGO_ENABLED", "true");

    expect(getAvailablePaymentMethods()[0].value).toBe("bank_transfer");
  });
});
