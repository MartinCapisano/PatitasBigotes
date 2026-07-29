/**
 * Presentación de productos por cantidad/peso (docs/products_by_measure.md).
 *
 * `quantity` cuenta pasos; el monto en la unidad de medida es `quantity * step`
 * (paso = 100 g ⇒ quantity 5 se muestra como "500 g"). Los productos por unidad
 * se muestran como "N u.".
 */

export type MeasureLike = {
  sold_by?: string | null;
  quantity: number;
  measure_unit?: string | null;
  step?: number | null;
};

export function isMeasureItem(item: { sold_by?: string | null }): boolean {
  return item.sold_by === "measure";
}

export function formatMeasureAmount(
  steps: number,
  measureUnit: string | null | undefined,
  step: number
): string {
  const amount = steps * step;
  const unit = (measureUnit ?? "").trim();
  return unit ? `${amount} ${unit}` : `${amount}`;
}

export function formatItemQuantity(item: MeasureLike): string {
  if (isMeasureItem(item)) {
    return formatMeasureAmount(item.quantity, item.measure_unit ?? null, item.step ?? 1);
  }
  return `${item.quantity} u.`;
}
