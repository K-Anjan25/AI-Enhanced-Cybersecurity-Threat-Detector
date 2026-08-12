export type UserRole = "ADMIN" | "ANALYST" | "USER" | "AUDITOR";

export interface UserAdminResponse {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_blocked: boolean;
  updatedAt?: string;
}

export interface MessageResponse {
  message: string;
}
