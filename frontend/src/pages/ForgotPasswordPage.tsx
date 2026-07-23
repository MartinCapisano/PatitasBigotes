import { Link } from "react-router-dom";
import { useForgotPasswordPage } from "../features/auth";

export function ForgotPasswordPage() {
  const forgotPasswordPage = useForgotPasswordPage();

  return (
    <section className="auth-wrap">
      <h1 className="page-title">Recuperar password</h1>
      <p className="page-subtitle">Ingresa tu email y, si la cuenta existe, te enviaremos un link para restablecer la password.</p>
      <form className="card auth-form" onSubmit={forgotPasswordPage.onSubmit}>
        <label>
          Email
          <input
            className="input"
            type="email"
            value={forgotPasswordPage.email}
            onChange={(event) => forgotPasswordPage.setEmail(event.target.value)}
            required
          />
        </label>
        {forgotPasswordPage.error && <p className="error">{forgotPasswordPage.error}</p>}
        {forgotPasswordPage.success && <p className="success">{forgotPasswordPage.success}</p>}
        <button
          className="btn"
          type="submit"
          disabled={forgotPasswordPage.loading || forgotPasswordPage.resendCooldownSeconds > 0}
        >
          {forgotPasswordPage.loading
            ? "Enviando..."
            : forgotPasswordPage.resendCooldownSeconds > 0
              ? `Reenviar en ${forgotPasswordPage.resendCooldownSeconds}s...`
              : "Enviar link"}
        </button>
        <p className="muted">
          <Link className="link-back" to="/login">Volver a ingresar</Link>
        </p>
      </form>
    </section>
  );
}
