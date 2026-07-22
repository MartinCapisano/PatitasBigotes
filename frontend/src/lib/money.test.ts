import { describe, expect, it } from "vitest";
import { formatArs, formatMoney } from "./money";

// es-AR separates the symbol from the number with a non-breaking space, so the
// amount never wraps away from its "$". Written as an escape because a literal
// one is indistinguishable from a plain space when reading this file.
const NBSP = "\u00a0";
const ars = (text: string) => `$${NBSP}${text}`;

describe("formatArs", () => {
  it("never rounds away the cents", () => {
    // The whole catalogue is priced at ",90". Rounding turns $ 99,90 into
    // $ 100: a price the shop does not charge and never chose.
    expect(formatArs(9990)).toBe(ars("99,90"));
    expect(formatArs(12990)).toBe(ars("129,90"));
    expect(formatArs(25990)).toBe(ars("259,90"));
    expect(formatArs(68990)).toBe(ars("689,90"));
  });

  it("keeps the cents visible on round amounts too", () => {
    // Otherwise the same amount renders differently depending on its value,
    // and a reader cannot tell "exact" from "rounded" at a glance.
    expect(formatArs(10000)).toBe(ars("100,00"));
    expect(formatArs(250000)).toBe(ars("2.500,00"));
  });

  it("formats zero", () => {
    expect(formatArs(0)).toBe(ars("0,00"));
  });

  it("groups thousands the way es-AR does", () => {
    expect(formatArs(123456789)).toBe(ars("1.234.567,89"));
  });

  it("renders a dash when there is no amount", () => {
    expect(formatArs(null)).toBe("-");
  });

  it("keeps a single cent from disappearing", () => {
    expect(formatArs(1)).toBe(ars("0,01"));
  });

  it("survives a discounted price that lands on an odd cent", () => {
    // 15% off $ 129,90 leaves $ 110,41 -- exactly the kind of number rounding
    // used to swallow.
    expect(formatArs(11041)).toBe(ars("110,41"));
  });
});

describe("formatMoney", () => {
  it("defaults to pesos", () => {
    expect(formatMoney(25990)).toBe(formatArs(25990));
  });

  it("falls back to pesos when the currency comes empty", () => {
    expect(formatMoney(25990, "")).toBe(formatArs(25990));
  });

  it("honours another currency without rounding it either", () => {
    expect(formatMoney(25990, "USD")).toContain("259,90");
  });

  it("renders a dash when there is no amount", () => {
    expect(formatMoney(null, "USD")).toBe("-");
  });
});
