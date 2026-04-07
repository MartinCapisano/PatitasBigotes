import { Link } from "react-router-dom";
import { useResetPasswordPage } from "../features/auth";

export function ResetPasswordPage() {
  const resetPasswordPage = useResetPasswordPage();

  return (
    <section className="auth-wrap">
      <h1 className="page-title">Restablecer password</h1>
      <p className="page-subtitle">
        {resetPasswordPage.tokenPresent
          ? "Ingresa tu nueva password para recuperar el acceso a tu cuenta."
          : "Este enlace no es valido o esta incompleto."}
      </p>

      {!resetPasswordPage.tokenPresent ? (
        <article className="card auth-form">
          <p className="error">No pudimos restablecer la password con este enlace. Solicita uno nuevo.</p>
          <div className="checkout-actions">
            <Link className="btn" to="/forgot-password">
              Solicitar nuevo enlace
            </Link>
            <Link className="btn btn-ghost" to="/login">
              Volver a ingresar
            </Link>
          </div>
          <p className="muted">
            <Link className="link-back" to="/home">Volver al inicio</Link>
          </p>
        </article>
      ) : (
        <form className="card auth-form" onSubmit={resetPasswordPage.onSubmit}>
          <label>
            Nueva password
            <input
              className="input"
              type="password"
              value={resetPasswordPage.newPassword}
              onChange={(event) => resetPasswordPage.setNewPassword(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </label>
          <label>
            Repetir nueva password
            <input
              className="input"
              type="password"
              value={resetPasswordPage.confirmPassword}
              onChange={(event) => resetPasswordPage.setConfirmPassword(event.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </label>
          <p className="muted">La password debe tener al menos 8 caracteres.</p>
          {resetPasswordPage.error && <p className="error">{resetPasswordPage.error}</p>}
          {resetPasswordPage.success && <p className="success">{resetPasswordPage.success}</p>}
          <button className="btn" type="submit" disabled={resetPasswordPage.loading || Boolean(resetPasswordPage.success)}>
            {resetPasswordPage.loading ? "Restableciendo..." : "Restablecer password"}
          </button>
          <div className="checkout-actions">
            <Link
              className="btn btn-small btn-ghost"
              to="/login"
              state={resetPasswordPage.success ? { reason: "password_reset_completed" } : undefined}
            >
              Ir al login
            </Link>
            <Link className="btn btn-small btn-ghost" to="/forgot-password">
              Solicitar nuevo enlace
            </Link>
          </div>
        </form>
      )}
    </section>
  );
}
