export type AuthUiErrorKind =
  | "network"
  | "unauthorized"
  | "forbidden"
  | "csrf"
  | "validation"
  | "conflict"
  | "server"
  | "unknown";

export type ErrorContext = "login" | "register" | "forgot-password" | "email-verify" | "checkout" | "profile" | "turns" | "generic";

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
  if (status !== null && status >= 500) {
    return { kind: "server", status, detail, isNetwork: false };
  }
  return { kind: "unknown", status, detail, isNetwork: false };
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
    if (classified.detail) {
      return classified.detail;
    }
    return "No se pudo solicitar la recuperacion de password.";
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

  if (context === "profile") {
    if (classified.kind === "network") {
      return "No se pudo conectar con el servidor para cargar o actualizar tu perfil.";
    }
    if (classified.kind === "csrf") {
      return "Origen no permitido para actualizar tu perfil.";
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
