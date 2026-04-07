import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { confirmPasswordReset } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";

const SUCCESS_REDIRECT_MS = 1800;

export function useResetPasswordPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const token = useMemo(() => new URLSearchParams(location.search).get("token")?.trim() || "", [location.search]);
  const tokenPresent = token.length > 0;
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => {
      navigate("/login", {
        replace: true,
        state: { reason: "password_reset_completed" }
      });
    }, SUCCESS_REDIRECT_MS);
    return () => window.clearTimeout(timer);
  }, [navigate, success]);

  function validateForm(): string | null {
    if (!tokenPresent) {
      return "Este enlace no es valido o esta incompleto. Solicita uno nuevo.";
    }
    if (!newPassword || !confirmPassword) {
      return "Completa y confirma tu nueva password para continuar.";
    }
    if (newPassword.length < 8) {
      return "La nueva password debe tener al menos 8 caracteres.";
    }
    if (newPassword !== confirmPassword) {
      return "Las passwords no coinciden.";
    }
    return null;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      setSuccess("");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await confirmPasswordReset(token, newPassword);
      setNewPassword("");
      setConfirmPassword("");
      setSuccess("Tu password fue actualizada. Ya puedes ingresar con la nueva password.");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "reset-password"));
    } finally {
      setLoading(false);
    }
  }

  return {
    tokenPresent,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    loading,
    error,
    success,
    onSubmit
  };
}
