import { useState, type FormEvent } from "react";
import { requestPasswordReset } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";
import { useEmailCooldown } from "./useEmailCooldown";

/**
 * Este formulario no necesita un boton de "reenviar": volver a mandarlo YA es
 * el reenvio -- genera un token nuevo y manda el mail otra vez. Y tiene el
 * mismo throttle de 20 s en el backend que el reenvio de verificacion, con el
 * mismo 429 en ingles. Mismo modo de falla, mismo cooldown.
 */
export function useForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const resendCooldown = useEmailCooldown("password-reset");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading || resendCooldown.active) return;

    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await requestPasswordReset(email.trim());
      resendCooldown.start();
      setSuccess("Si la cuenta existe y el email ya fue verificado, te enviamos un link para restablecer la password.");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "forgot-password"));
    } finally {
      setLoading(false);
    }
  }

  return {
    email,
    setEmail,
    loading,
    error,
    success,
    resendCooldownSeconds: resendCooldown.remainingSeconds,
    onSubmit
  };
}
