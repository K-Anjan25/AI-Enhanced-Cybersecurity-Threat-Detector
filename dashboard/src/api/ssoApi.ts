import axiosInstance from "./axios";

export interface SsoConfig {
  enabled: boolean;
  provider_type?: string;
  display_name?: string;
  issuer?: string;
  client_id?: string;
  scopes?: string;
  jit?: boolean;
  source?: string;
  // SAML
  sso_url?: string;
  entity_id?: string;
  acs_url?: string;
  metadata_url?: string;
  // New nested for Phase 41
  oidc?: SsoConfig;
  saml?: SsoConfig;
}

export async function fetchSsoConfig(): Promise<SsoConfig> {
  const { data } = await axiosInstance.get("/auth/sso/config");
  return data;
}

export function getSsoLoginUrl(type: "oidc" | "saml" = "oidc"): string {
  const base = axiosInstance.defaults.baseURL || "/api/v1";
  if (type === "saml") {
    return `${base}/auth/sso/saml/login`;
  }
  return `${base}/auth/sso/login`;
}

export interface SsoProvider {
  id?: number;
  provider_type: string;
  display_name: string;
  issuer?: string;
  client_id?: string;
  scopes?: string;
  saml_metadata_url?: string;
  saml_entity_id?: string;
  saml_acs_url?: string;
  saml_sso_url?: string;
  enabled: boolean;
  jit_provisioning: boolean;
}

export async function fetchSsoProviders(): Promise<{ org: SsoConfig; global: SsoConfig }> {
  const { data } = await axiosInstance.get("/admin/sso/providers");
  return data;
}

export async function upsertSsoProvider(payload: {
  provider_type: string;
  display_name?: string;
  issuer?: string;
  client_id?: string;
  client_secret?: string;
  scopes?: string;
  saml_metadata_url?: string;
  saml_entity_id?: string;
  saml_acs_url?: string;
  saml_sso_url?: string;
  saml_certificate?: string;
  enabled: boolean;
  jit_provisioning: boolean;
}): Promise<SsoProvider> {
  const { data } = await axiosInstance.post("/admin/sso/providers", payload);
  return data;
}

export async function deleteSsoProvider(providerType?: string): Promise<{ deleted: number }> {
  const url = providerType ? `/admin/sso/providers?provider_type=${providerType}` : "/admin/sso/providers";
  const { data } = await axiosInstance.delete(url);
  return data;
}

export interface ScimTokenInfo {
  id: number;
  name: string;
  prefix: string;
  created_by?: string;
  created_at?: string;
  last_used_at?: string;
  is_active: boolean;
}

export async function fetchScimTokens(): Promise<{ data: ScimTokenInfo[] }> {
  const { data } = await axiosInstance.get("/admin/scim/tokens");
  return data;
}

export async function createScimToken(name: string): Promise<{ id: number; name: string; prefix: string; token: string; message: string }> {
  const { data } = await axiosInstance.post("/admin/scim/tokens", { name });
  return data;
}

export async function deleteScimToken(id: number): Promise<{ deleted: number }> {
  const { data } = await axiosInstance.delete(`/admin/scim/tokens/${id}`);
  return data;
}
