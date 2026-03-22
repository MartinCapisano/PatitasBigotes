import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toUserMessage } from "../../../services/http-errors";

export function useLoginPage(login: (email: string, password: string) => Promise<boolean>) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState =
    typeof location.state === "object" && location.state !== null
      ? (location.state as {
          from?: string;
          checkoutEmail?: string;
          reason?: string;
        })
      : null;
  const redirectTo = locationState?.from === "/checkout" ? "/checkout" : null;
  const [email, setEmail] = useState(locationState?.checkoutEmail ?? "");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const infoMessage =
    locationState?.reason === "registered_account_checkout"
      ? "Ese email ya tiene cuenta. Inicia sesion para continuar con tu carrito."
      : "";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const admin = await login(email, password);
      if (redirectTo) {
        navigate(redirectTo, { replace: true });
        return;
      }
      navigate(admin ? "/admin" : "/profile");
    } catch (err: unknown) {
      setError(toUserMessage(err, "login"));
    } finally {
      setLoading(false);
    }
  }

  return {
    email,
    setEmail,
    password,
    setPassword,
    loading,
    infoMessage,
    error,
    onSubmit
  };
}
