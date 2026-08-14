import api from "./axios";
import { 
  LoginForm, 
  User, 
  UserProfile, 
  PasswordResetRequest, 
  PasswordResetPayload, 
  UpdatePasswordPayload 
} from "../types/user";

// --- User Profile & Authentication Supporting Endpoints ---

export const requestPasswordReset = async (email: string): Promise<{ message: string }> => {
  const { data } = await api.post("/forgot-password", { email });
  return data;
};

export const resetPassword = async (payload: PasswordResetPayload): Promise<{ message: string }> => {
  const { data } = await api.post("/reset-password", payload);
  return data;
};

export const registerUser = async (payload: Record<string, any>): Promise<User> => {
  const { data } = await api.post("/register", payload);
  return data;
};

export const getProfile = async (): Promise<UserProfile> => {
  const { data } = await api.get("/user/profile");
  return data;
};

export const updateProfile = async (payload: Record<string, any>): Promise<UserProfile> => {
  const { data } = await api.put("/user/profile", payload);
  return data;
};

export const updatePassword = async (payload: UpdatePasswordPayload): Promise<{ message: string }> => {
  const { data } = await api.put("/user/updatePassword", payload);
  return data;
};

// Unified Export Object
export const UserApi = {
  requestPasswordReset,
  resetPassword,
  registerUser,
  getProfile,
  updateProfile,
  updatePassword,
};

export default UserApi;