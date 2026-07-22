import { describe, expect, it } from "vitest";
import { normalizePaymentAmountsForOrder } from "./useAdminRegisterPayment";
import { formatArs } from "../../../lib/money";

/**
 * The invariant this file exists for: the amount the admin reads on screen has
 * to be an amount they can type back.
 *
 * It did not hold. The pending amount was rendered with a formatter that
 * rounded, so a $ 259,90 payment displayed as "$ 260"; typing "260" was
 * rejected with "Monto pagado invalido", and the message did not say what the
 * right number was. The admin could not confirm a payment by copying what the
 * app told them. Every price in the catalogue ends in ",90", so this was not an
 * edge case.
 */
const REAL_WORLD_AMOUNTS = [
  9990, // $ 99,90  - the ",90" pricing used across the catalogue
  25990,
  68990,
  11041, // what 15% off $ 129,90 leaves: an odd cent
  10000, // a round amount, to be sure the cents suffix does not break it
  1 // a single cent
];

describe("normalizePaymentAmountsForOrder", () => {
  it.each(REAL_WORLD_AMOUNTS)(
    "accepts the amount exactly as the screen renders it (%i cents)",
    (totalCents) => {
      const onScreen = formatArs(totalCents);

      expect(
        normalizePaymentAmountsForOrder({
          paidRaw: onScreen,
          changeRaw: "0",
          totalCents,
          method: "bank_transfer"
        })
      ).toEqual({ paidCents: totalCents, changeCents: 0 });
    }
  );

  it("rejects an amount that does not match the order total", () => {
    // 25990 cents is $ 259,90; someone typing $ 260 is paying a different price.
    expect(
      normalizePaymentAmountsForOrder({
        paidRaw: "260,00",
        changeRaw: "0",
        totalCents: 25990,
        method: "bank_transfer"
      })
    ).toBeNull();
  });

  it("accepts cash where the paid amount minus the change equals the total", () => {
    expect(
      normalizePaymentAmountsForOrder({
        paidRaw: formatArs(30000),
        changeRaw: formatArs(4010),
        totalCents: 25990,
        method: "cash"
      })
    ).toEqual({ paidCents: 30000, changeCents: 4010 });
  });

  it("rejects an empty or non numeric amount", () => {
    for (const paidRaw of ["", "   ", "abc"]) {
      expect(
        normalizePaymentAmountsForOrder({
          paidRaw,
          changeRaw: "0",
          totalCents: 25990,
          method: "bank_transfer"
        })
      ).toBeNull();
    }
  });
});
