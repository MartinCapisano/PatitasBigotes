import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
// Render's free tier sleeps after ~15 min idle and takes 30-60s to answer the
// first request on wake, so the timeout must tolerate that cold start in
// production. Overridable via VITE_API_TIMEOUT_MS; falls back to 60s.
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 60000;
const AUTH_ROUTES_WITH_LOCAL_HANDLING = ["/auth/login", "/auth/logout", "/auth/refresh"];

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

function shouldSkipUnauthorizedBroadcast(url: string | undefined): boolean {
  if (!url) return false;
  const normalized = String(url).split("?")[0];
  return AUTH_ROUTES_WITH_LOCAL_HANDLING.some(
    (route) => normalized === route || normalized.endsWith(route)
  );
}

export const http = axios.create({
  baseURL,
  timeout: API_TIMEOUT_MS,
  withCredentials: true
});

let refreshPromise: Promise<void> | null = null;

async function refreshAccessToken(): Promise<void> {
  const { refreshSession } = await import("./auth-api");
  await refreshSession();
}

function broadcastUnauthorized() {
  window.dispatchEvent(new CustomEvent("pb-auth-unauthorized"));
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const requestConfig = error.config as RetriableRequestConfig | undefined;
    const requestUrl = requestConfig?.url;
    if (error.response?.status !== 401 || !requestConfig) {
      return Promise.reject(error);
    }

    if (shouldSkipUnauthorizedBroadcast(requestUrl) || requestConfig._retry) {
      broadcastUnauthorized();
      return Promise.reject(error);
    }

    requestConfig._retry = true;

    try {
      if (refreshPromise === null) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      await refreshPromise;
      return http(requestConfig);
    } catch (refreshError) {
      broadcastUnauthorized();
      return Promise.reject(refreshError);
    }
  }
);
