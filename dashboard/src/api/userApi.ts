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

export const getUsers = async (): Promise<User[]> => {
  const { data } = await api.get("/users");
  return data;
};

export const createUser = async (payload: Record<string, any>): Promise<User> => {
  const { data } = await api.post("/users", payload);
  return data;
};
export const deleteUser = async (id: string | number): Promise<{ success: boolean }> => {
  const { data } = await api.delete(`/users/${id}`);
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

// --- Admin Endpoints ---

export const updateUserRole = async (userId: string, role: string): Promise<User> => {
  const { data } = await api.patch(`/admin/users/${userId}`, { role });
  return data;
};

export const toggleUserBlockStatus = async (userId: string, isBlocked: boolean): Promise<User> => {
  const { data } = await api.patch(`/admin/users/${userId}/block`, { is_blocked: isBlocked });
  return data;
};

export const deleteUserAccount = async (userId: string): Promise<{ success: boolean }> => {
  const { data } = await api.delete(`/admin/users/${userId}`);
  return data;
};

export const toggleUserStatus = async (userId: string, isActive: boolean): Promise<User> => {
  const { data } = await api.patch(`/admin/users/${userId}`, { is_active: isActive });
  return data;
};

// Unified Export Object
export const UserApi = {
  requestPasswordReset,
  resetPassword,
  registerUser,
  getUsers,
  createUser,
  deleteUser,
  getProfile,
  updateProfile,
  updatePassword,
  updateUserRole,
  toggleUserBlockStatus,
  deleteUserAccount,
  toggleUserStatus,
};

export default UserApi;