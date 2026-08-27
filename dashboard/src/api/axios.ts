import axios from "axios";

// Same-origin relative base by default: the Vite dev server proxies /api to the
// backend (vite.config.mjs) and nginx does the same in production
// (dashboard/nginx.conf). REACT_APP_BASE_URL can still override it.
const BASE_URL = import.meta.env.REACT_APP_BASE_URL || "/api/v1";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  // JWTs live in httpOnly cookies set by the backend, so cookies are sent
  // with every request and the XSS-exposed JS never sees a token.
  withCredentials: true,
});

// ---------------------------------------------------------------------------
// Session-expiry handling: on a 401 from any protected endpoint, try one
// refresh (single-flight — concurrent failures share one request), then retry
// the original call once. If refresh fails, clear the local session flags and
// send the user to /login. Auth endpoints are exempt so wrong-password on the
// login form (a legit 401) neither loops nor redirects.
// ---------------------------------------------------------------------------
const AUTH_EXEMPT = ["/login", "/register", "/refresh", "/forgot-password", "/reset-password"];
const SESSION_FLAG_KEYS = ["auth_status", "user_role", "username", "user_permissions"];

let refreshInFlight: Promise<boolean> | null = null;

const tryRefreshSession = (): Promise<boolean> => {
  if (!refreshInFlight) {
    refreshInFlight = api
      .post("/refresh")
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
};

const clearLocalSession = (): void => {
  SESSION_FLAG_KEYS.forEach((key) => localStorage.removeItem(key));
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error?.config ?? {};
    const status = error?.response?.status;
    const isExempt = AUTH_EXEMPT.some((path) => String(config.url ?? "").includes(path));
    if (status !== 401 || config.__retried || isExempt) {
      return Promise.reject(error);
    }
    const refreshed = await tryRefreshSession();
    if (!refreshed) {
      clearLocalSession();
      return Promise.reject(error);
    }
    config.__retried = true;
    return api.request(config);
  }
);

export default api;
