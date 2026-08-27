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

export default api;
