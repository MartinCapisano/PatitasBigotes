import { Link } from "react-router-dom";
import { useVerifyEmailPage } from "../features/auth";

export function VerifyEmailPage() {
  const verifyEmailPage = useVerifyEmailPage();

  return (
    <section className="auth-wrap">
      <h1 className="page-title">Verificar email</h1>
      <p className="page-subtitle">
        {verifyEmailPage.tokenPresent
          ? "Estamos validando el link de verificacion de tu cuenta."
          : "Te enviamos un email de verificacion para activar tu cuenta."}
      </p>
      <article className="card auth-form">
        {!verifyEmailPage.tokenPresent ? (
          <p className="muted">
            {verifyEmailPage.email
              ? `Email enviado a ${verifyEmailPage.email}.`
              : "Si acabas de registrarte, revisa tu bandeja de entrada y spam."}
          </p>
        ) : null}
        {verifyEmailPage.loading ? <p className="muted">Procesando verificacion...</p> : null}
        {verifyEmailPage.error && <p className="error">{verifyEmailPage.error}</p>}
        {verifyEmailPage.success && <p className="success">{verifyEmailPage.success}</p>}
        {!verifyEmailPage.tokenPresent ? (
          <button
            className="btn"
            type="button"
            onClick={() => void verifyEmailPage.onResendVerification()}
            disabled={verifyEmailPage.loading || !verifyEmailPage.email}
          >
            {verifyEmailPage.loading ? "Reenviando..." : "Reenviar email"}
          </button>
        ) : null}
        <p className="muted">
          <Link className="link-back" to="/home">Volver al inicio</Link>
        </p>
      </article>
    </section>
  );
}
