export type AuthUiErrorKind =
  | "network"
  | "unauthorized"
  | "forbidden"
  | "csrf"
  | "validation"
  | "conflict"
  | "rate-limit"
  | "server"
  | "unknown";

export type ErrorContext =
  | "login"
  | "register"
  | "forgot-password"
  | "reset-password"
  | "email-verify"
  | "checkout"
  | "payment-return"
  | "profile"
  | "turns"
  | "generic";

export class AuthFlowError extends Error {
  code: "login_ok_profile_failed" | "session_bootstrap_failed";

  constructor(code: "login_ok_profile_failed" | "session_bootstrap_failed", message: string) {
    super(message);
    this.name = "AuthFlowError";
    this.code = code;
  }
}

type ClassifiedHttpError = {
  kind: AuthUiErrorKind;
  status: number | null;
  detail: string | null;
  isNetwork: boolean;
};

function extractDetail(error: unknown): string | null {
  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof error.response === "object" &&
    error.response !== null &&
    "data" in error.response &&
    typeof error.response.data === "object" &&
    error.response.data !== null &&
    "detail" in error.response.data
  ) {
    const detail = (error.response.data as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
    if (Array.isArray(detail)) {
      const joined = detail
        .map((item) => {
          if (typeof item === "string") return item.trim();
          if (typeof item === "object" && item !== null && "msg" in item) {
            const msg = (item as { msg?: unknown }).msg;
            return typeof msg === "string" ? msg.trim() : "";
          }
          return "";
        })
        .filter(Boolean)
        .join(" | ");
      return joined || null;
    }
    return null;
  }
  return null;
}

export function classifyHttpError(error: unknown): ClassifiedHttpError {
  const status =
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof error.response === "object" &&
    error.response !== null &&
    "status" in error.response &&
    typeof error.response.status === "number"
      ? error.response.status
      : null;
  const code =
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof (error as { code?: unknown }).code === "string"
      ? String((error as { code?: unknown }).code)
      : "";
  const isNetwork = code === "ERR_NETWORK" || code === "ECONNABORTED";
  const detail = extractDetail(error);

  if (isNetwork) {
    return { kind: "network", status, detail, isNetwork: true };
  }
  if (status === 401) {
    return { kind: "unauthorized", status, detail, isNetwork: false };
  }
  if (status === 403 && detail === "csrf origin check failed") {
    return { kind: "csrf", status, detail, isNetwork: false };
  }
  if (status === 403) {
    return { kind: "forbidden", status, detail, isNetwork: false };
  }
  if (status === 422) {
    return { kind: "validation", status, detail, isNetwork: false };
  }
  if (status === 409) {
    return { kind: "conflict", status, detail, isNetwork: false };
  }
  if (status === 429) {
    return { kind: "rate-limit", status, detail, isNetwork: false };
  }
  if (status !== null && status >= 500) {
    return { kind: "server", status, detail, isNetwork: false };
  }
  return { kind: "unknown", status, detail, isNetwork: false };
}

/**
 * Red de seguridad para el 429 de los envios de email.
 *
 * El cooldown del boton (`useEmailCooldown`) impide que el usuario *provoque*
 * este error con un click, pero no cubre dos pestanas abiertas ni los limites
 * por ventana (6 cada 10 min) o por IP (20). Cuando el 429 llegue igual, que no
 * llegue en ingles: el backend manda "please wait before retrying verification"
 * y sin esto se mostraba crudo.
 */
const EMAIL_RATE_LIMIT_MESSAGE =
  "Estas pidiendo emails muy seguido. Espera unos minutos e intenta de nuevo.";

function retryPaymentMessage(detail: string | null): string | null {
  if (detail === "retry not allowed: order cancelled") {
    return "La orden ya fue cancelada y ya no admite reintentos de pago.";
  }
  if (detail === "retry not allowed: order cancelled because stock reservation expired") {
    return "La orden ya fue cancelada porque vencio la reserva de stock.";
  }
  if (detail === "retry not allowed: order is no longer submitted") {
    return "La orden ya no esta disponible para reintentar el pago.";
  }
  if (detail === "retry not allowed: stock reservation expired") {
    return "La reserva de stock vencio. Ya no podemos reintentar este pago.";
  }
  if (detail === "retry not allowed: payment state changed") {
    return "Este pago ya no puede reintentarse desde aqui.";
  }
  if (detail === "retry not allowed: order already paid") {
    return "La orden ya fue abonada y no necesita un nuevo intento.";
  }
  if (detail === "retry failed: mercadopago checkout unavailable") {
    return "No pudimos generar un nuevo checkout de Mercado Pago. Intenta nuevamente en unos minutos.";
  }
  if (detail === "order not found" || detail === "payment not found") {
    return "No encontramos la compra que intentas pagar.";
  }
  return null;
}

export function toUserMessage(error: unknown, context: ErrorContext): string {
  if (error instanceof AuthFlowError) {
    if (error.code === "login_ok_profile_failed") {
      return "Ingreso exitoso, pero no pudimos cargar tu perfil. Reintenta.";
    }
    if (error.code === "session_bootstrap_failed") {
      return "No pudimos validar tu sesion en este momento.";
    }
  }

  const classified = classifyHttpError(error);
  if (context === "login") {
    if (classified.kind === "unauthorized") {
      return "Email o contrasena incorrectos.";
    }
    if (classified.kind === "forbidden" && classified.detail === "email not verified") {
      return "Tu email no esta verificado.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido. Revisa URL del frontend/backend.";
    }
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor.";
    }
    if (classified.kind === "server") {
      return "Error interno del servidor. Intenta nuevamente en unos minutos.";
    }
    return "No se pudo iniciar sesion.";
  }

  if (context === "register") {
    if (classified.kind === "csrf") {
      return "Origen no permitido. Revisa URL del frontend/backend.";
    }
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para crear tu cuenta.";
    }
    if (classified.kind === "server") {
      return "Error interno del servidor. Intenta nuevamente en unos minutos.";
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo crear la cuenta.";
  }

  if (context === "forgot-password") {
    if (classified.kind === "csrf") {
      return "Origen no permitido. Revisa URL del frontend/backend.";
    }
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para enviar el email de recuperacion.";
    }
    if (classified.kind === "server") {
      return "Error interno del servidor. Intenta nuevamente en unos minutos.";
    }
    if (classified.kind === "rate-limit") {
      return EMAIL_RATE_LIMIT_MESSAGE;
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo solicitar la recuperacion de password.";
  }

  if (context === "reset-password") {
    if (classified.kind === "csrf") {
      return "Origen no permitido. Revisa URL del frontend/backend.";
    }
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para restablecer tu password.";
    }
    if (classified.kind === "server") {
      return "Error interno del servidor. Intenta nuevamente en unos minutos.";
    }
    if (classified.kind === "rate-limit") {
      return EMAIL_RATE_LIMIT_MESSAGE;
    }
    if (classified.kind === "validation" || classified.kind === "forbidden" || classified.kind === "conflict") {
      return "No pudimos restablecer la password con este enlace. Solicita uno nuevo.";
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo restablecer la password.";
  }

  if (context === "email-verify") {
    if (classified.kind === "csrf") {
      return "Origen no permitido. Revisa URL del frontend/backend.";
    }
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para enviar o reenviar el email de verificacion.";
    }
    if (classified.kind === "server") {
      return "Error interno del servidor. Intenta nuevamente en unos minutos.";
    }
    if (classified.kind === "rate-limit") {
      return EMAIL_RATE_LIMIT_MESSAGE;
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo gestionar la verificacion del email.";
  }

  if (context === "checkout") {
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para finalizar la compra.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido para la operacion de checkout.";
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo finalizar la compra.";
  }

  if (context === "payment-return") {
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para consultar el pago.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido para consultar el pago.";
    }
    const retryMessage = retryPaymentMessage(classified.detail);
    if (retryMessage) {
      return retryMessage;
    }
    if (classified.detail === "public_status_token is required") {
      return "No encontramos el identificador publico del pago.";
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo consultar el estado actualizado del pago.";
  }

  if (context === "profile") {
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para cargar o actualizar tu perfil.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido para actualizar tu perfil.";
    }
    const retryMessage = retryPaymentMessage(classified.detail);
    if (retryMessage) {
      return retryMessage;
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo completar la operacion de perfil.";
  }

  if (context === "turns") {
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para solicitar el turno.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido para solicitar turnos.";
    }
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo solicitar el turno.";
  }

  if (classified.detail) {
    return classified.detail;
  }
  if (classified.kind === "network") {
    return "No se pudo conectar con el servidor.";
  }
  if (classified.kind === "server") {
    return "Error interno del servidor.";
  }
  return "Ocurrio un error inesperado.";
}
