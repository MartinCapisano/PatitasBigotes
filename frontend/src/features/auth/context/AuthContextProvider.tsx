import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getMyProfile, login as loginApi, logout as logoutApi } from "../../../services/auth-api";
import { AuthFlowError } from "../../../services/http-errors";

export type AuthContextValue = {
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  sessionExpired: boolean;
  clearSessionExpiredNotice: () => void;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function bootstrapSession() {
      setIsLoading(true);
      try {
        const profile = await getMyProfile();
        if (!mounted) return;
        setIsAuthenticated(true);
        setIsAdmin(Boolean(profile.is_admin));
        setSessionExpired(false);
      } catch {
        if (!mounted) return;
        setIsAuthenticated(false);
        setIsAdmin(false);
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    void bootstrapSession();

    function handleUnauthorized() {
      if (!mounted) return;
      setIsAuthenticated(false);
      setIsAdmin(false);
      setIsLoading(false);
      setSessionExpired(true);
    }

    window.addEventListener("pb-auth-unauthorized", handleUnauthorized);
    return () => {
      mounted = false;
      window.removeEventListener("pb-auth-unauthorized", handleUnauthorized);
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isLoading,
      isAuthenticated,
      isAdmin,
      sessionExpired,
      clearSessionExpiredNotice() {
        setSessionExpired(false);
      },
      async login(email: string, password: string) {
        setIsLoading(true);
        try {
          await loginApi(email, password);
          let profile;
          try {
            profile = await getMyProfile();
          } catch {
            setIsAuthenticated(false);
            setIsAdmin(false);
            throw new AuthFlowError(
              "login_ok_profile_failed",
              "Login succeeded but profile loading failed"
            );
          }
          const adminFlag = Boolean(profile.is_admin);
          setIsAuthenticated(true);
          setIsAdmin(adminFlag);
          setSessionExpired(false);
          return adminFlag;
        } finally {
          setIsLoading(false);
        }
      },
      async logout() {
        try {
          await logoutApi();
        } catch {
          // best effort: if backend logout fails, local auth state must still clear
        }
        setIsAuthenticated(false);
        setIsAdmin(false);
        setSessionExpired(false);
      }
    }),
    [isAuthenticated, isAdmin, isLoading, sessionExpired]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
