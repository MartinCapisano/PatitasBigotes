import { describe, expect, it } from "vitest";
import { formatItemQuantity, formatMeasureAmount, isMeasureItem } from "./measure";

describe("measure formatting", () => {
  it("formats steps into the measure amount (paso=100g, 5 pasos => 500 g)", () => {
    expect(formatMeasureAmount(5, "g", 100)).toBe("500 g");
    expect(formatMeasureAmount(1, "ml", 250)).toBe("250 ml");
  });

  it("falls back to the raw amount when there is no unit", () => {
    expect(formatMeasureAmount(3, null, 100)).toBe("300");
  });

  it("formats a measure cart item as its amount and a unit item as N u.", () => {
    expect(
      formatItemQuantity({ sold_by: "measure", quantity: 7, measure_unit: "g", step: 100 })
    ).toBe("700 g");
    expect(formatItemQuantity({ sold_by: "unit", quantity: 2 })).toBe("2 u.");
    // Carrito viejo sin sold_by => se trata como unidad.
    expect(formatItemQuantity({ quantity: 3 })).toBe("3 u.");
  });

  it("detects measure items", () => {
    expect(isMeasureItem({ sold_by: "measure" })).toBe(true);
    expect(isMeasureItem({ sold_by: "unit" })).toBe(false);
    expect(isMeasureItem({})).toBe(false);
  });
});
