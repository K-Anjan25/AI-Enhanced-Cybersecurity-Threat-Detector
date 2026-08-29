import React, { useEffect, useState } from "react";
import { PageHeader, Card, Button } from "../../../components/ui";
import { fetchSsoProviders, upsertSsoProvider, deleteSsoProvider, fetchScimTokens, createScimToken, deleteScimToken, type ScimTokenInfo } from "../../../api/ssoApi";
import { getApiError } from "../../../utils/getApiError";
import { showSuccess } from "../../../utils/showSuccess";

export default function SsoScimPage(): React.ReactElement {
  const [providerType, setProviderType] = useState<"oidc" | "saml">("oidc");
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const [ssoIssuer, setSsoIssuer] = useState("");
  const [ssoClientId, setSsoClientId] = useState("");
  const [ssoClientSecret, setSsoClientSecret] = useState("");
  const [ssoDisplayName, setSsoDisplayName] = useState("Corporate SSO");
  const [ssoJit, setSsoJit] = useState(true);
  const [ssoScopes, setSsoScopes] = useState("openid email profile");
  // SAML
  const [samlMetadataUrl, setSamlMetadataUrl] = useState("");
  const [samlEntityId, setSamlEntityId] = useState("");
  const [samlSsoUrl, setSamlSsoUrl] = useState("");
  const [samlAcsUrl, setSamlAcsUrl] = useState("");
  const [samlCert, setSamlCert] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [scimTokens, setScimTokens] = useState<ScimTokenInfo[]>([]);
  const [newTokenName, setNewTokenName] = useState("SCIM Provisioning Token");
  const [lastCreatedToken, setLastCreatedToken] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const sso = await fetchSsoProviders();
      // org may contain oidc and saml
      const org = sso.org || sso.global;
      const oidc = org?.oidc || (org?.provider_type === "oidc" ? org : null);
      const saml = org?.saml || (org?.provider_type === "saml" ? org : null);

      if (oidc?.enabled) {
        setProviderType("oidc");
        setSsoEnabled(true);
        setSsoIssuer(oidc.issuer || "");
        setSsoClientId(oidc.client_id || "");
        setSsoDisplayName(oidc.display_name || "Corporate SSO");
        setSsoScopes(oidc.scopes || "openid email profile");
        setSsoJit(oidc.jit ?? true);
      }
      if (saml?.enabled) {
        setProviderType("saml");
        setSsoEnabled(true);
        setSsoDisplayName(saml.display_name || "Corporate SAML SSO");
        setSamlMetadataUrl(saml.metadata_url || "");
        setSamlEntityId(saml.entity_id || "");
        setSamlSsoUrl(saml.sso_url || "");
        setSamlAcsUrl(saml.acs_url || "");
        setSsoJit(saml.jit ?? true);
      }

      const scim = await fetchScimTokens();
      setScimTokens(scim.data || []);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load SSO/SCIM config"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSaveSso = async () => {
    setSaving(true);
    setError(null);
    try {
      if (!ssoEnabled) {
        await deleteSsoProvider(providerType);
        showSuccess(`SSO ${providerType.toUpperCase()} provider disabled`);
        await load();
        return;
      }
      if (providerType === "oidc") {
        if (!ssoIssuer || !ssoClientId) {
          setError("Issuer and Client ID are required for OIDC");
          setSaving(false);
          return;
        }
        await upsertSsoProvider({
          provider_type: "oidc",
          display_name: ssoDisplayName,
          issuer: ssoIssuer,
          client_id: ssoClientId,
          client_secret: ssoClientSecret || undefined,
          scopes: ssoScopes,
          enabled: true,
          jit_provisioning: ssoJit,
        });
      } else {
        if (!samlSsoUrl && !samlMetadataUrl) {
          setError("SSO URL or Metadata URL is required for SAML");
          setSaving(false);
          return;
        }
        await upsertSsoProvider({
          provider_type: "saml",
          display_name: ssoDisplayName,
          saml_metadata_url: samlMetadataUrl || undefined,
          saml_entity_id: samlEntityId || undefined,
          saml_acs_url: samlAcsUrl || undefined,
          saml_sso_url: samlSsoUrl || undefined,
          saml_certificate: samlCert || undefined,
          enabled: true,
          jit_provisioning: ssoJit,
        } as any);
      }
      showSuccess(`SSO ${providerType.toUpperCase()} provider saved`);
      setSsoClientSecret("");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to save SSO provider"));
    } finally {
      setSaving(false);
    }
  };

  const handleCreateScimToken = async () => {
    setError(null);
    try {
      const res = await createScimToken(newTokenName);
      setLastCreatedToken(res.token);
      showSuccess("SCIM token created — copy it now");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to create SCIM token"));
    }
  };

  const handleDeleteScimToken = async (id: number) => {
    if (!confirm("Delete this SCIM token? Provisioning clients using it will stop working.")) return;
    try {
      await deleteScimToken(id);
      showSuccess("SCIM token deleted");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to delete SCIM token"));
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader title="SSO & SCIM" description="Enterprise authentication and provisioning." />
        <p className="text-sm text-content-tertiary">Loading…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="SSO & SCIM"
        description="Configure OIDC + SAML single sign-on and SCIM provisioning (Users, Groups, Bulk) for enterprise IdPs. SAML verifies signature if xmlsec available, else logs warning and parses without verification — documented gap."
      />

      {error && (
        <div role="alert" className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {lastCreatedToken && (
        <div className="px-4 py-3 rounded-lg bg-status-warning/10 border border-status-warning/30 text-sm">
          <p className="font-semibold text-content-primary">Copy this token now — it will not be shown again:</p>
          <code className="mt-2 block p-2 bg-app-subtle rounded text-xs break-all font-mono">{lastCreatedToken}</code>
          <p className="mt-2 text-xs text-content-tertiary">Use as Bearer token for SCIM: Authorization: Bearer &lt;token&gt; → /scim/v2/Users, /Groups, /Bulk</p>
          <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLastCreatedToken(null)}>Dismiss</Button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* SSO */}
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-1">Single Sign-On — OIDC + SAML 2.0 (Phase 41)</h3>
          <p className="text-xs text-content-tertiary mb-4">OIDC Authorization Code + SAML SP-initiated. JIT creates USER/ANALYST (never ADMIN). Secrets encrypted at rest.</p>

          <div className="space-y-3">
            <div className="flex gap-2">
              <select value={providerType} onChange={(e) => setProviderType(e.target.value as any)} className="px-2 py-1 rounded bg-app-subtle border border-line-subtle text-xs">
                <option value="oidc">OIDC</option>
                <option value="saml">SAML 2.0</option>
              </select>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={ssoEnabled} onChange={(e) => setSsoEnabled(e.target.checked)} />
                <span className="font-semibold">Enable {providerType.toUpperCase()}</span>
              </label>
            </div>

            <div>
              <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Display Name</label>
              <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={ssoDisplayName} onChange={(e) => setSsoDisplayName(e.target.value)} placeholder={providerType === "oidc" ? "Corporate SSO" : "Corporate SAML SSO"} />
            </div>

            {providerType === "oidc" ? (
              <>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Issuer URL</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={ssoIssuer} onChange={(e) => setSsoIssuer(e.target.value)} placeholder="https://accounts.google.com or https://login.microsoftonline.com/tenant/v2.0" />
                  <p className="text-[10px] text-content-tertiary mt-1">Discovery via /.well-known/openid-configuration</p>
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Client ID</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={ssoClientId} onChange={(e) => setSsoClientId(e.target.value)} placeholder="oidc client id" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Client Secret (encrypted at rest)</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" type="password" value={ssoClientSecret} onChange={(e) => setSsoClientSecret(e.target.value)} placeholder="Leave blank to keep existing" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Scopes</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={ssoScopes} onChange={(e) => setSsoScopes(e.target.value)} placeholder="openid email profile" />
                </div>
              </>
            ) : (
              <>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Metadata URL (optional, auto-fills SSO URL + cert)</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={samlMetadataUrl} onChange={(e) => setSamlMetadataUrl(e.target.value)} placeholder="https://idp.example.com/metadata" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">IdP SSO URL</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={samlSsoUrl} onChange={(e) => setSamlSsoUrl(e.target.value)} placeholder="https://idp.example.com/sso" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">SP Entity ID</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={samlEntityId} onChange={(e) => setSamlEntityId(e.target.value)} placeholder="https://noctra.example.com" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">ACS URL (optional)</label>
                  <input className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={samlAcsUrl} onChange={(e) => setSamlAcsUrl(e.target.value)} placeholder="/api/v1/auth/sso/saml/callback" />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">IdP Certificate (for signature verification, optional)</label>
                  <textarea className="mt-1 w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-xs font-mono" rows={3} value={samlCert} onChange={(e) => setSamlCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." />
                  <p className="text-[10px] text-content-tertiary mt-1">If xmlsec not installed, verification skipped with warning — documented gap.</p>
                </div>
              </>
            )}

            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={ssoJit} onChange={(e) => setSsoJit(e.target.checked)} />
              <span>JIT provisioning — create user on first login</span>
            </label>

            <Button variant="primary" size="sm" onClick={handleSaveSso} disabled={saving}>{saving ? "Saving…" : ssoEnabled ? `Save ${providerType.toUpperCase()} Provider` : `Disable ${providerType.toUpperCase()}`}</Button>

            <div className="pt-2 space-y-1">
              <p className="text-[10px] text-content-tertiary">OIDC Callback: <code className="bg-app-subtle px-1 rounded">/api/v1/auth/sso/callback</code></p>
              <p className="text-[10px] text-content-tertiary">SAML ACS: <code className="bg-app-subtle px-1 rounded">/api/v1/auth/sso/saml/callback</code> (POST SAMLResponse + RelayState)</p>
              <p className="text-[10px] text-content-tertiary">SAML Login: <code className="bg-app-subtle px-1 rounded">/api/v1/auth/sso/saml/login</code> (SP-initiated)</p>
            </div>
          </div>
        </Card>

        {/* SCIM */}
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-1">SCIM 2.0 Provisioning — Users + Groups + Bulk (Phase 41)</h3>
          <p className="text-xs text-content-tertiary mb-4">Bearer token per-org, hashed at rest. Endpoints: /scim/v2/Users, /Groups with membership sync, /Bulk (max 20 ops), discovery.</p>

          <div className="space-y-3">
            <div className="flex gap-2">
              <input className="flex-1 px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={newTokenName} onChange={(e) => setNewTokenName(e.target.value)} placeholder="Token name" />
              <Button variant="secondary" size="sm" onClick={handleCreateScimToken}>Create Token</Button>
            </div>

            <div className="space-y-2">
              {scimTokens.length === 0 ? (
                <p className="text-xs text-content-tertiary">No SCIM tokens — create one to enable provisioning from Okta/Entra ID.</p>
              ) : (
                scimTokens.map((t) => (
                  <div key={t.id} className="flex items-center justify-between p-2 rounded-lg bg-app-subtle border border-line-subtle">
                    <div>
                      <p className="text-xs font-semibold text-content-primary">{t.name} <span className="font-mono text-[10px] text-content-tertiary">({t.prefix}…)</span></p>
                      <p className="text-[10px] text-content-tertiary">Created {t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"} {t.last_used_at ? `· Last used ${new Date(t.last_used_at).toLocaleDateString()}` : "· Never used"}</p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => handleDeleteScimToken(t.id)}>Delete</Button>
                  </div>
                ))
              )}
            </div>

            <div className="pt-3 border-t border-line-subtle space-y-1">
              <p className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">IdP Configuration</p>
              <p className="text-[11px] text-content-secondary">SCIM Base URL: <code className="bg-app-subtle px-1 rounded">/scim/v2</code></p>
              <p className="text-[11px] text-content-secondary">Auth: Bearer token (value shown once)</p>
              <p className="text-[11px] text-content-secondary">Users: CRUD + filter userName/email/externalId eq, PATCH active</p>
              <p className="text-[11px] text-content-secondary">Groups: CRUD + filter displayName/externalId eq, members sync via PUT/PATCH add/remove/replace</p>
              <p className="text-[11px] text-content-secondary">Bulk: POST /scim/v2/Bulk max 20 ops, failOnErrors support, supports POST Users/Groups, PUT/PATCH/DELETE Users, DELETE Groups</p>
              <p className="text-[10px] text-content-tertiary">Groups role mapping not automatic — manual via User role. Bulk fails fast if failOnErrors set.</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
