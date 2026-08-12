const AUTH_FLAG_KEY = "auth_status";

export interface TokenPayload {
  accessToken?: string;
  refreshToken?: string;
  access_token?: string;
  refresh_token?: string;
}

/**
 * Auth tokens now live exclusively in httpOnly, SameSite cookies set by the
 * backend, so they are invisible to JavaScript and safe against XSS.
 *
 * setToken / getToken / removeToken are kept as a thin, non-sensitive auth
 * state flag used purely for client-side route gating. No JWT is persisted.
 */
export const setToken = (_payload: TokenPayload): void => {
  localStorage.setItem(AUTH_FLAG_KEY, "1");
};

/**
 * Returns "1" when an authenticated session is active (cookie held by browser).
 */
export const getToken = (): string | null => {
  return localStorage.getItem(AUTH_FLAG_KEY);
};

/**
 * Clears the local auth-state flag. The httpOnly cookies are cleared by the
 * backend's /logout endpoint.
 */
export const removeToken = (): void => {
  localStorage.removeItem(AUTH_FLAG_KEY);
};
