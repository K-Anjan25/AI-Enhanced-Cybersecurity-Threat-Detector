import axios from "axios";

// 1. Define base URL with fallback to prevent invalid URL crashes
const BASE_URL = import.meta.env.REACT_APP_BASE_URL || "http://localhost:8000/api/v1";

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
