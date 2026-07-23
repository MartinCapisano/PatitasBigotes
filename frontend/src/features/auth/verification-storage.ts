const PENDING_VERIFY_EMAIL_KEY = "pb_pending_verify_email";

export function savePendingVerificationEmail(email: string): void {
  const normalizedEmail = email.trim();
  if (!normalizedEmail) return;
  window.sessionStorage.setItem(PENDING_VERIFY_EMAIL_KEY, normalizedEmail);
}

export function readPendingVerificationEmail(): string {
  return window.sessionStorage.getItem(PENDING_VERIFY_EMAIL_KEY)?.trim() || "";
}

export function clearPendingVerificationEmail(): void {
  window.sessionStorage.removeItem(PENDING_VERIFY_EMAIL_KEY);
}

/**
 * Segundos que el boton de reenviar queda bloqueado despues de un envio.
 *
 * El backend usa 20 s (`EMAIL_MIN_INTERVAL_SECONDS`). Aca van 30 a proposito:
 * si el front copiara el 20 y alguien subiera el backend a 40, se
 * desincronizan y el 429 vuelve. Con 30 el desfasaje solo puede jugar a favor.
 */
export const EMAIL_COOLDOWN_SECONDS = 30;

/** Los dos envios tienen contadores distintos en el backend, asi que aca tambien. */
export type EmailCooldownScope = "verification" | "password-reset";

const COOLDOWN_KEY_PREFIX = "pb_email_cooldown_";

/**
 * Persistido, no en memoria: sin esto un refresh de pagina resetea el contador
 * y el 429 -- que es el error que este cooldown existe para evitar -- vuelve.
 */
export function startEmailCooldown(scope: EmailCooldownScope, now: number = Date.now()): void {
  window.sessionStorage.setItem(COOLDOWN_KEY_PREFIX + scope, String(now));
}

export function readEmailCooldownRemainingSeconds(
  scope: EmailCooldownScope,
  now: number = Date.now()
): number {
  const raw = window.sessionStorage.getItem(COOLDOWN_KEY_PREFIX + scope);
  if (!raw) return 0;

  const startedAt = Number(raw);
  if (!Number.isFinite(startedAt)) return 0;

  const elapsedSeconds = (now - startedAt) / 1000;
  // Un reloj que salta hacia atras no puede dejar el boton trabado para siempre.
  if (elapsedSeconds < 0) return 0;

  const remaining = Math.ceil(EMAIL_COOLDOWN_SECONDS - elapsedSeconds);
  return remaining > 0 ? remaining : 0;
}
