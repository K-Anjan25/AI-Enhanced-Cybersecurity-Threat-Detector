import { api } from "./axios";
import type { User } from "../types/user";

export interface OrgInfo {
  id: number;
  name: string;
  slug: string;
  description?: string | null;
  user_count: number;
  created_at?: string | null;
}

export interface RolePermissionMatrix {
  data: { role: string; clearance: number; permissions: string[] }[];
  clearance_requirements: Record<string, number>;
}

export interface RosterParams {
  org_id?: number | string;
  role?: string;
  search?: string;
}

export interface AdminRosterMember extends User {
  id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  is_blocked?: boolean;
  clearance_level?: number | null;
  department?: string | null;
  org_id?: number | null;
  org_name?: string | null;
  created_at?: string | null;
}

export const fetchOrgs = async (): Promise<{ data: OrgInfo[]; total: number }> => {
  const { data } = await api.get<{ data: OrgInfo[]; total: number }>("/admin/orgs");
  return data;
};

export const fetchRolesMatrix = async (): Promise<RolePermissionMatrix> => {
  const { data } = await api.get<RolePermissionMatrix>("/admin/roles");
  return data;
};

export const fetchRoster = async (params: RosterParams): Promise<AdminRosterMember[]> => {
  const { data } = await api.get<AdminRosterMember[]>("/users", { params });
  return data;
};

export const createRosterUser = async (payload: Record<string, any>): Promise<AdminRosterMember> => {
  const { data } = await api.post<AdminRosterMember>("/users", payload);
  return data;
};

export const updateRosterUser = async (userId: number, payload: Record<string, any>): Promise<Record<string, any>> => {
  const { data } = await api.patch(`/admin/users/${userId}`, payload);
  return data;
};

export const deleteRosterUser = async (userId: number): Promise<{ success: boolean }> => {
  const { data } = await api.delete<{ success: boolean }>(`/admin/users/${userId}`);
  return data;
};

export const AdminApi = {
  fetchOrgs,
  fetchRolesMatrix,
  fetchRoster,
  createRosterUser,
  updateRosterUser,
  deleteRosterUser,
};

export default AdminApi;