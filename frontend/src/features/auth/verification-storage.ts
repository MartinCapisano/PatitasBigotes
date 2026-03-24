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
