import * as Sentry from "@sentry/react";

// Error tracking + tracing/APM del frontend. Se activa solo si hay VITE_SENTRY_DSN;
// sin DSN es un no-op, así dev y los tests nunca mandan eventos.
//
// - browserTracingIntegration: mide pageloads y navegaciones (Web Vitals, latencia)
//   y propaga la traza al backend, encadenando el APM de las dos capas.
// - sendDefaultPii: false a propósito (no adjuntar datos del usuario por defecto).
// - tracesSampleRate bajo (default 0.2) para no quemar la cuota del free tier.
export function initSentry(): void {
  const dsn = String(import.meta.env.VITE_SENTRY_DSN ?? "").trim();
  if (!dsn) return;

  const rawRate = Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE);
  const tracesSampleRate = Number.isFinite(rawRate) ? Math.min(Math.max(rawRate, 0), 1) : 0.2;

  Sentry.init({
    dsn,
    environment: String(import.meta.env.MODE ?? "production"),
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate,
    sendDefaultPii: false,
  });
}
