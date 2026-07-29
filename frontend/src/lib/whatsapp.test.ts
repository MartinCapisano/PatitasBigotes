import { describe, expect, it } from "vitest";
import { buildAvailabilityMessage, buildWhatsappUrl } from "./whatsapp";
import type { CartItem } from "./cart-storage";

const measureItem: CartItem = {
  product_id: 1,
  product_name: "Alimento a granel",
  variant_id: 10,
  option_label: "Granel",
  unit_price: 200,
  quantity: 5,
  img_url: null,
  sold_by: "measure",
  measure_unit: "g",
  step: 100
};

const unitItem: CartItem = {
  product_id: 2,
  product_name: "Collar",
  variant_id: 20,
  option_label: "M / Azul",
  unit_price: 1500,
  quantity: 2,
  img_url: null,
  sold_by: "unit"
};

describe("buildWhatsappUrl", () => {
  it("keeps only digits of the number and url-encodes the message", () => {
    const url = buildWhatsappUrl("hola mundo", "+54 9 351 123 4567");
    expect(url).toBe("https://wa.me/5493511234567?text=hola%20mundo");
  });

  it("falls back to a numberless wa.me link when no number is given", () => {
    expect(buildWhatsappUrl("hi", "")).toBe("https://wa.me/?text=hi");
  });
});

describe("buildAvailabilityMessage", () => {
  it("lists every item, flags the measure ones and sums the estimated total", () => {
    const message = buildAvailabilityMessage([measureItem, unitItem]);
    expect(message).toContain("Alimento a granel — 500 g (por cantidad)");
    expect(message).toContain("Collar — 2 u.");
    // total = 200*5 + 1500*2 = 4000
    expect(message).toContain("Total estimado:");
    expect(message).toContain("40,00"); // formatArs divide por 100 => $ 40,00
  });

  it("appends the customer contact when provided", () => {
    const message = buildAvailabilityMessage([unitItem], {
      first_name: "Ana",
      last_name: "Pérez",
      email: "ana@example.com",
      phone: "1122334455"
    });
    expect(message).toContain("Mis datos: Ana Pérez · ana@example.com · 1122334455");
  });

  it("omits the contact line when there is no customer data", () => {
    const message = buildAvailabilityMessage([unitItem]);
    expect(message).not.toContain("Mis datos:");
  });
});
