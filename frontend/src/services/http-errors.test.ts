import { describe, expect, it } from "vitest";
import { classifyHttpError, toUserMessage, type ErrorContext } from "./http-errors";

/** Un 429 tal como lo devuelve el backend, con el detail en ingles. */
function throttled(detail: string) {
  return { response: { status: 429, data: { detail } } };
}

const EMAIL_CONTEXTS: ErrorContext[] = ["email-verify", "forgot-password", "reset-password"];

describe("classifyHttpError", () => {
  it("gives 429 its own kind instead of leaving it as unknown", () => {
    expect(classifyHttpError(throttled("please wait")).kind).toBe("rate-limit");
  });
});

describe("toUserMessage con un 429 de email", () => {
  it.each(EMAIL_CONTEXTS)("responde en castellano en el contexto %s", (context) => {
    // El cooldown del boton evita que el usuario provoque este error, pero no
    // cubre dos pestanas ni los limites por ventana o por IP. Cuando llega
    // igual, no puede llegar en ingles.
    const message = toUserMessage(throttled("please wait before retrying verification"), context);

    expect(message).not.toContain("please wait");
    expect(message).toBe("Estas pidiendo emails muy seguido. Espera unos minutos e intenta de nuevo.");
  });

  it("no se traga el detail de los errores que no son 429", () => {
    const message = toUserMessage(
      { response: { status: 400, data: { detail: "token already used" } } },
      "email-verify"
    );

    expect(message).toBe("token already used");
  });
});
