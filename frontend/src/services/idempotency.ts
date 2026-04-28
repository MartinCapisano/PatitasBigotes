export function buildIdempotencyKey(prefix: string): string {
  const normalizedPrefix = prefix.trim() || "request";
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${normalizedPrefix}_${crypto.randomUUID()}`;
  }
  return `${normalizedPrefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}
