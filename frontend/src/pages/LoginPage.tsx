import { useAuth } from "../auth/AuthContext";
import { useLoginPage } from "../features/auth";
import { Link } from "react-router-dom";

export function LoginPage() {
  const { login, clearSessionExpiredNotice } = useAuth();
  const loginPage = useLoginPage(login);

  return (
    <section className="auth-wrap">
      <h1 className="page-title">Ingresar</h1>
      <form className="card auth-form" onSubmit={loginPage.onSubmit}>
        {loginPage.infoMessage && <p className="muted">{loginPage.infoMessage}</p>}
        <label>
          Email
          <input
            className="input"
            type="email"
            value={loginPage.email}
            onChange={(event) => loginPage.setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            className="input"
            type="password"
            value={loginPage.password}
            onChange={(event) => loginPage.setPassword(event.target.value)}
            required
          />
        </label>
        {loginPage.error && <p className="error">{loginPage.error}</p>}
        <button className="btn" type="submit" disabled={loginPage.loading}>
          {loginPage.loading ? "Ingresando..." : "Entrar"}
        </button>
        <Link className="btn btn-ghost" to="/home" onClick={clearSessionExpiredNotice}>
          Continuar sin iniciar sesion
        </Link>
        <Link className="btn btn-ghost" to="/forgot-password">
          Has olvidado la contrasenia?
        </Link>
        <p className="muted">
          No tienes cuenta? <Link className="link-back" to="/register">Crear cuenta</Link>
        </p>
      </form>
    </section>
  );
}
