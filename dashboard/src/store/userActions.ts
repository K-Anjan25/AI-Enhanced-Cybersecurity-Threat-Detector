import { AxiosError } from "axios";
import { api } from "../api/axios";
import { UserError } from "../types/error";
import {
  Login,
  LoginForm,
  User,
  UserDispatch,
} from "../types/user";
import { removeToken, setToken } from "../utils/token";
import { ProfileForm, ProfileImage } from "../types/profile";

interface AuthResponse {
  access_token?: string;
  refresh_token?: string;
  accessToken?: string;
  refreshToken?: string;
  role?: string;
  username?: string;
  permissions?: string[];
}

const normalizeUser = (payload: any): User => {
  const u = payload?.user ?? payload ?? {};
  const roles = Array.isArray(u?.roles)
    ? u.roles
    : [String(u?.role || "user").toUpperCase()];
  return {
    userId: u?.id?.toString() ?? u?.userId ?? "",
    email: u?.email ?? "",
    username: u?.username ?? "",
    role: u?.role,
    roles,
    permissions: Array.isArray(payload?.permissions) ? payload.permissions : [],
    clearanceLevel: u?.clearance_level ?? u?.clearanceLevel,
    department: u?.department,
    profileImageURL: u?.profileImageURL ?? u?.profile_image ?? "",
  };
};

const getErrorMessage = (error: AxiosError<UserError>): string => {
  const data = error.response?.data as any;
  return data?.detail || data?.message || error.message || "Something went wrong";
};

const isAuthFailure = (status?: number): boolean =>
  status === 401 || status === 403 || status === 422;

export const login = (creds: LoginForm) => async (dispatch: UserDispatch) => {
  dispatch({ type: "LOGIN_START" });
  try {
    const formData = new URLSearchParams();
    formData.append("username", (creds as any).identifier || (creds as any).username || (creds as any).email);
    formData.append("password", creds.password);

    const { data } = await api.post<AuthResponse>("/login", formData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    });

    setToken(data);
    if (data.role) localStorage.setItem("user_role", data.role);
    if (data.username) localStorage.setItem("username", data.username);
    if (Array.isArray(data.permissions)) {
      localStorage.setItem("user_permissions", JSON.stringify(data.permissions));
    }
    dispatch({ type: "LOGIN_SUCCESS" });
    dispatch(userMe() as any);
  } catch (error) {
    const err = error as AxiosError<UserError>;
    dispatch({
      type: "LOGIN_ERROR",
      payload: getErrorMessage(err),
    });
  }
};

export const userMe = () => async (dispatch: UserDispatch) => {
  dispatch({ type: "USER_START" });
  try {
    const { data } = await api.get<any>("/me");
    const normalized = normalizeUser(data);
    if (Array.isArray(normalized.permissions)) {
      localStorage.setItem("user_permissions", JSON.stringify(normalized.permissions));
    }
    if (normalized.role) localStorage.setItem("user_role", normalized.role);
    if (normalized.username) localStorage.setItem("username", normalized.username);
    dispatch({ type: "USER_SUCCESS", payload: normalized });
  } catch (error) {
    const err = error as AxiosError<UserError>;
    if (isAuthFailure(err.response?.status)) {
      dispatch({ type: "USER_ERROR" });
      dispatch(refreshToken() as any);
    } else {
      // Network/server failure: stop loading so the app is not stuck on the
      // global fallback loader; the user can retry via login.
      dispatch({ type: "USER_ERROR" });
    }
  }
};

export const logout = () => async (dispatch: UserDispatch) => {
  try {
    // Clears the httpOnly cookies server-side; best-effort, ignore failures.
    await api.post("/logout");
  } catch {
    // no-op: local state is cleared regardless
  } finally {
    removeToken();
    localStorage.removeItem("user_role");
    localStorage.removeItem("username");
    localStorage.removeItem("user_permissions");
    dispatch({ type: "LOGOUT" });
  }
};

export const refreshToken = () => async (dispatch: UserDispatch) => {
  // The refresh token now lives in an httpOnly cookie, so it is sent
  // automatically with credentials. No manual header is needed.
  try {
    const { data } = await api.post<AuthResponse>("/refresh");
    setToken(data);
    dispatch(userMe() as any);
  } catch (error) {
    const err = error as AxiosError<UserError>;
    if (isAuthFailure(err.response?.status)) {
      removeToken();
      localStorage.removeItem("user_role");
      localStorage.removeItem("username");
      localStorage.removeItem("user_permissions");
      dispatch({ type: "REFRESH_TOKEN_ERROR" });
    }
  }
};

export const updateProfile =
  (res: Login, user: ProfileForm) => async (dispatch: UserDispatch) => {
    setToken(res);
    dispatch({ type: "UPDATE_PROFILE", payload: user });
  };

export const updateProfileImage =
  (profileImage: ProfileImage) => async (dispatch: UserDispatch) => {
    dispatch({ type: "UPDATE_PROFILE_IMAGE", payload: profileImage });
  };
