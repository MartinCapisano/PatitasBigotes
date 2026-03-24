import { useState, type FormEvent } from "react";
import { requestPasswordReset } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";

export function useForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;

    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await requestPasswordReset(email.trim());
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
    onSubmit
  };
}
