import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { clearPendingVerificationEmail, readPendingVerificationEmail } from "../features/auth/verification-storage";
import { cartCount, subscribeToCartUpdates } from "../lib/cart-storage";
import type { NotificationItem } from "../types";
import { getUnreadNotificationCount, listNotifications, readAllNotifications, readNotification } from "../services/notifications-api";

export function Layout() {
  const location = useLocation();
  const { isAuthenticated, logout } = useAuth();
  const [currentCartCount, setCurrentCartCount] = useState(() => cartCount());
  const isAdminRoute = location.pathname.startsWith("/admin");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [pendingVerificationEmail, setPendingVerificationEmail] = useState("");

  useEffect(() => {
    setPendingVerificationEmail(readPendingVerificationEmail());
  }, [location.pathname]);

  useEffect(() => {
    function syncCartCount() {
      setCurrentCartCount(cartCount());
    }

    syncCartCount();
    const unsubscribe = subscribeToCartUpdates(syncCartCount);
    window.addEventListener("storage", syncCartCount);
    return () => {
      unsubscribe();
      window.removeEventListener("storage", syncCartCount);
    };
  }, []);

  const loadUnreadCount = useCallback(async () => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      return;
    }
    try {
      const count = await getUnreadNotificationCount();
      setUnreadCount(count);
    } catch {
      // fail silently in topbar
    }
  }, [isAuthenticated]);

  const loadNotifications = useCallback(async () => {
    if (!isAuthenticated) {
      setNotifications([]);
      return;
    }
    setNotificationsLoading(true);
    try {
      const response = await listNotifications({ limit: 20, offset: 0 });
      setNotifications(response.data);
    } catch {
      // fail silently in topbar
    } finally {
      setNotificationsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setNotifications([]);
      setUnreadCount(0);
      return;
    }
    void loadUnreadCount();
  }, [isAuthenticated, loadUnreadCount]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void loadUnreadCount();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [isAuthenticated, loadUnreadCount]);

  useEffect(() => {
    if (!notificationsOpen) return;
    void loadNotifications();
  }, [notificationsOpen, loadNotifications]);

  async function onReadNotification(item: NotificationItem) {
    if (item.is_read) return;
    try {
      await readNotification(item.id);
      setNotifications((prev) => prev.map((row) => (row.id === item.id ? { ...row, is_read: true } : row)));
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // noop
    }
  }

  async function onReadAllNotifications() {
    try {
      await readAllNotifications();
      setNotifications((prev) => prev.map((row) => ({ ...row, is_read: true })));
      setUnreadCount(0);
    } catch {
      // noop
    }
  }

  return (
    <div className="app-root">
      <header className="topbar">
        <div className="container topbar-inner">
          <Link className="brand" to="/home">
            <span className="brand-main">Patitas</span>
            <span className="brand-amp">&nbsp;y&nbsp;</span>
            <span className="brand-main">Bigotes</span>
          </Link>
          <nav className="nav">
            <Link to="/home">Tienda</Link>
            <Link to="/checkout">Carrito ({currentCartCount})</Link>
            {isAuthenticated && <Link to="/profile">Mi cuenta</Link>}
            {isAuthenticated && (
              <div className="notifications-wrap">
                <button
                  className="notifications-bell-btn"
                  type="button"
                  onClick={() => setNotificationsOpen((prev) => !prev)}
                  aria-label="Abrir notificaciones"
                >
                  <svg
                    className="notifications-bell-icon"
                    viewBox="0 0 24 24"
                    role="img"
                    aria-hidden="true"
                  >
                    <path d="M12 3a5 5 0 0 0-5 5v2.8c0 .9-.3 1.8-.9 2.5L4.5 15a1 1 0 0 0 .7 1.7h13.6a1 1 0 0 0 .7-1.7l-1.6-1.7a3.8 3.8 0 0 1-.9-2.5V8a5 5 0 0 0-5-5Z" />
                    <path d="M9.5 18.5a2.5 2.5 0 0 0 5 0" />
                  </svg>
                  {unreadCount > 0 ? <span className="notifications-badge">{unreadCount}</span> : null}
                </button>
                {notificationsOpen && (
                  <div className="notifications-dropdown">
                    <div className="notifications-header">
                      <strong>Notificaciones</strong>
                      <button className="btn btn-small btn-ghost" type="button" onClick={() => void onReadAllNotifications()}>
                        Marcar todas leidas
                      </button>
                    </div>
                    {notificationsLoading ? (
                      <p className="muted">Cargando...</p>
                    ) : notifications.length === 0 ? (
                      <p className="muted">Sin notificaciones.</p>
                    ) : (
                      <div className="notifications-list">
                        {notifications.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className={`notifications-item ${item.is_read ? "notifications-item-read" : ""}`}
                            onClick={() => void onReadNotification(item)}
                          >
                            <strong>{item.title}</strong>
                            <span>{item.message}</span>
                            <span className="muted">{new Date(item.created_at).toLocaleString()}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {!isAuthenticated ? (
              <Link className="btn btn-small" to="/login">
                Ingresar
              </Link>
            ) : (
              <button className="btn btn-small btn-ghost" onClick={() => void logout()} type="button">
                Salir
              </button>
            )}
          </nav>
        </div>
        <div className="container">
          <nav className="menu-tabs" aria-label="Navegacion principal">
            <Link
              to="/home"
              className={location.pathname === "/home" ? "menu-tab menu-tab-active" : "menu-tab"}
            >
              Tienda
            </Link>
            <Link
              to="/peluqueria"
              className={location.pathname === "/peluqueria" ? "menu-tab menu-tab-active" : "menu-tab"}
            >
              Peluqueria
            </Link>
            <Link
              to="/contacto"
              className={location.pathname === "/contacto" ? "menu-tab menu-tab-active" : "menu-tab"}
            >
              Contacto
            </Link>
          </nav>
        </div>
      </header>
      {!isAuthenticated && location.pathname === "/home" && pendingVerificationEmail ? (
        <div className="container">
          <div className="card" style={{ marginTop: 16, padding: 16 }}>
            <div className="admin-inline-actions" style={{ justifyContent: "space-between", gap: 12 }}>
              <div>
                <p style={{ margin: 0, fontWeight: 700 }}>Verifica tu email</p>
                <p className="muted">
                  Enviamos un email a {pendingVerificationEmail}. Puedes verificar ahora o hacerlo mas tarde.
                </p>
              </div>
              <div className="admin-inline-actions">
                <Link className="btn btn-small" to="/verify-email">
                  Verificar
                </Link>
                <button
                  className="btn btn-small btn-ghost"
                  type="button"
                  onClick={() => {
                    clearPendingVerificationEmail();
                    setPendingVerificationEmail("");
                  }}
                >
                  Omitir
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      <main className={isAdminRoute ? "container page page-admin" : "container page"}>
        <Outlet />
      </main>
    </div>
  );
}
