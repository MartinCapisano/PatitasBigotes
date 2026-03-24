import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function ProtectedRoute() {
  const { isLoading, isAuthenticated, sessionExpired } = useAuth();
  if (isLoading) {
    return <p>Cargando sesion...</p>;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={sessionExpired ? { reason: "session_expired" } : undefined} />;
  }
  return <Outlet />;
}
