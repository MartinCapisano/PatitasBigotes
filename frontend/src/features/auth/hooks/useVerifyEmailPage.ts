import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { confirmEmailVerification, requestEmailVerification } from "../../../services/auth-api";
import { toUserMessage } from "../../../services/http-errors";
import { clearPendingVerificationEmail, readPendingVerificationEmail } from "../verification-storage";
import { useAuth } from "../../../auth/AuthContext";

export function useVerifyEmailPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [tokenProcessed, setTokenProcessed] = useState(false);

  useEffect(() => {
    setEmail(readPendingVerificationEmail());
  }, []);

  useEffect(() => {
    const token = new URLSearchParams(location.search).get("token")?.trim() || "";
    if (tokenProcessed) return;
    if (!token) {
      setTokenProcessed(true);
      setError("No pudimos validar este link de verificacion. Solicita un nuevo email de confirmacion desde tu perfil.");
      setSuccess("");
      if (isAuthenticated) {
        window.setTimeout(() => {
          navigate("/profile", { replace: true });
        }, 1800);
      }
      return;
    }

    let active = true;
    async function run() {
      setLoading(true);
      setError("");
      setSuccess("");
      try {
        await confirmEmailVerification(token);
        if (!active) return;
        clearPendingVerificationEmail();
        setEmail("");
        setSuccess("Cuenta verificada correctamente. Redirigiendo al inicio...");
      } catch {
        if (!active) return;
        setError("No pudimos validar este link de verificacion. Solicita un nuevo email de confirmacion desde tu perfil.");
        if (isAuthenticated) {
          window.setTimeout(() => {
            navigate("/profile", { replace: true });
          }, 1800);
        }
      } finally {
        if (active) {
          setLoading(false);
          setTokenProcessed(true);
        }
      }
    }

    void run();
    return () => {
      active = false;
    };
  }, [isAuthenticated, location.search, navigate, tokenProcessed]);

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => {
      navigate("/home", { replace: true });
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [navigate, success]);

  async function onResendVerification() {
    const normalizedEmail = email.trim();
    if (!normalizedEmail || loading) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await requestEmailVerification(normalizedEmail);
      setSuccess("Reenviamos el email de verificacion. Revisa tu bandeja y spam.");
    } catch (apiError: unknown) {
      setError(toUserMessage(apiError, "email-verify"));
    } finally {
      setLoading(false);
    }
  }

  return {
    email,
    loading,
    error,
    success,
    tokenPresent: Boolean(new URLSearchParams(location.search).get("token")?.trim()),
    onResendVerification
  };
}
