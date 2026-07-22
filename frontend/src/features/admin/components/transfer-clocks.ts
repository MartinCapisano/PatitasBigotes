/**
 * The two clocks the admin reads on a pending transfer.
 *
 * Kept out of the component so they can be tested on their own -- and because
 * the payment's own `expires_at` is *not* one of them: for a transfer it governs
 * nothing. The reservation is what actually cancels the order.
 */
const HOUR_MS = 60 * 60 * 1000;

/** How long this transfer has been waiting for someone to look at it. */
export function formatWaiting(createdAt: string, now: number = Date.now()): string {
  const created = new Date(createdAt).getTime();
  if (!Number.isFinite(created)) return "-";
  const hours = Math.floor(Math.max(0, now - created) / HOUR_MS);
  if (hours < 1) return "hace menos de 1 h";
  if (hours < 24) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} d ${hours % 24} h`;
}

/**
 * How long is left before the stock reservation cancels the order.
 *
 * This is what tells the admin which rows are about to fall off the queue and
 * take the sale with them, so it rounds down: promising an hour that is not
 * fully there would be the wrong direction to be wrong in.
 */
export function formatReservationDeadline(
  expiresAt: string | null,
  now: number = Date.now()
): string {
  if (!expiresAt) return "sin reserva activa";
  const expires = new Date(expiresAt).getTime();
  if (!Number.isFinite(expires)) return "-";
  const remainingHours = Math.floor((expires - now) / HOUR_MS);
  if (remainingHours < 0) return "reserva vencida";
  if (remainingHours < 1) return "vence en menos de 1 h";
  return `vence en ${remainingHours} h`;
}
