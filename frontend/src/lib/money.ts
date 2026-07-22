/**
 * The one place money becomes text.
 *
 * Amounts travel as integer cents end to end, and every one of them is a real
 * number someone acts on: a price the customer decides to pay, a total they
 * transfer, an amount the admin types to confirm a payment. So nothing here
 * rounds. A rounded amount is not a shorter version of the truth, it is a
 * different number -- `$ 99,90` shown as `$ 100` overstates the price and
 * throws away the `,90` the shop chose on purpose.
 *
 * This used to live in three copies (storefront, checkout, admin) plus an
 * inline fourth, all with `maximumFractionDigits: 0`. One implementation means
 * the next display cannot drift away from the others.
 */
export function formatMoney(cents: number | null, currency: string = "ARS"): string {
  if (cents === null) return "-";
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: currency || "ARS",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(cents / 100);
}

export function formatArs(cents: number | null): string {
  return formatMoney(cents, "ARS");
}

/**
 * The same amount, without the currency symbol, ready to sit in a text input.
 *
 * Prefilling an amount field is only safe if what lands there is typeable back:
 * `$ 260` in a box that expects `259,90` is exactly the trap that made the
 * admin unable to confirm a payment by copying what the screen showed.
 */
export function formatAmountForInput(cents: number | null): string {
  if (cents === null) return "";
  return new Intl.NumberFormat("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(cents / 100);
}
