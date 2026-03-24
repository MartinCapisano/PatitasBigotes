import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { register as registerApi } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";
import { savePendingVerificationEmail } from "../verification-storage";

export function useRegisterPage() {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading) return;

    const normalizedPassword = password;
    const normalizedConfirmPassword = confirmPassword;
    if (normalizedPassword !== normalizedConfirmPassword) {
      setError("Las contrasenas no coinciden.");
      setSuccess("");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const normalizedEmail = email.trim();
      await registerApi({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: normalizedEmail,
        password: normalizedPassword
      });
      savePendingVerificationEmail(normalizedEmail);
      setSuccess("Cuenta creada. Te enviamos un email de verificacion antes de tu primer ingreso.");
      window.setTimeout(() => {
        navigate("/home", { replace: true });
      }, 1200);
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "register"));
    } finally {
      setLoading(false);
    }
  }

  return {
    firstName,
    setFirstName,
    lastName,
    setLastName,
    email,
    setEmail,
    password,
    setPassword,
    confirmPassword,
    setConfirmPassword,
    loading,
    error,
    success,
    onSubmit
  };
}
