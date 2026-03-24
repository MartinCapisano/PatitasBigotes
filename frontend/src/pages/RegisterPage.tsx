import { Link } from "react-router-dom";
import { useRegisterPage } from "../features/auth";

export function RegisterPage() {
  const registerPage = useRegisterPage();

  return (
    <section className="auth-wrap">
      <h1 className="page-title">Crear cuenta</h1>
      <p className="page-subtitle">Registra tu cuenta para seguir tus pedidos y operar con acceso propio.</p>
      <form className="card auth-form" onSubmit={registerPage.onSubmit}>
        <label>
          Nombre
          <input
            className="input"
            value={registerPage.firstName}
            onChange={(event) => registerPage.setFirstName(event.target.value)}
            required
          />
        </label>
        <label>
          Apellido
          <input
            className="input"
            value={registerPage.lastName}
            onChange={(event) => registerPage.setLastName(event.target.value)}
            required
          />
        </label>
        <label>
          Email
          <input
            className="input"
            type="email"
            value={registerPage.email}
            onChange={(event) => registerPage.setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Contrasena
          <input
            className="input"
            type="password"
            value={registerPage.password}
            onChange={(event) => registerPage.setPassword(event.target.value)}
            required
          />
        </label>
        <label>
          Repetir contrasena
          <input
            className="input"
            type="password"
            value={registerPage.confirmPassword}
            onChange={(event) => registerPage.setConfirmPassword(event.target.value)}
            required
          />
        </label>
        <p className="muted">La contrasena debe tener al menos 8 caracteres y un caracter especial.</p>
        {registerPage.error && <p className="error">{registerPage.error}</p>}
        {registerPage.success && <p className="success">{registerPage.success}</p>}
        <button className="btn" type="submit" disabled={registerPage.loading}>
          {registerPage.loading ? "Creando cuenta..." : "Crear cuenta"}
        </button>
        <p className="muted">
          Ya tienes cuenta? <Link className="link-back" to="/login">Ingresa aqui</Link>
        </p>
      </form>
    </section>
  );
}
