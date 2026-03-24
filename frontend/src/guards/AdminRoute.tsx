import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function AdminRoute() {
  const { isLoading, isAuthenticated, isAdmin, sessionExpired } = useAuth();
  if (isLoading) {
    return <p>Cargando sesion...</p>;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={sessionExpired ? { reason: "session_expired" } : undefined} />;
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
