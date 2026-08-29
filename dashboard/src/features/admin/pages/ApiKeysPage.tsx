import React, { useEffect, useState } from "react";
import { PageHeader, Card, Button } from "../../../components/ui";
import { fetchApiKeys, createApiKey, revokeApiKey, fetchServiceAccounts, createServiceAccount, revokeServiceAccount, fetchRateLimitStatus, type ApiKeyInfo, type ServiceAccountInfo, type RateLimitStatus } from "../../../api/apikeyApi";
import { getApiError } from "../../../utils/getApiError";
import { showSuccess } from "../../../utils/showSuccess";

export default function ApiKeysPage(): React.ReactElement {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [sas, setSas] = useState<ServiceAccountInfo[]>([]);
  const [rl, setRl] = useState<RateLimitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newKeyName, setNewKeyName] = useState("CI/CD Pipeline Key");
  const [newKeyScopes, setNewKeyScopes] = useState("alerts:read,alerts:write");
  const [newKeyExpiry, setNewKeyExpiry] = useState<number | undefined>(90);
  const [newKeySaId, setNewKeySaId] = useState<number | undefined>(undefined);
  const [lastCreatedRaw, setLastCreatedRaw] = useState<string | null>(null);

  const [newSaName, setNewSaName] = useState("automation-bot");
  const [newSaDesc, setNewSaDesc] = useState("Service account for automation");
  const [newSaRole, setNewSaRole] = useState("service");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [k, s, r] = await Promise.all([fetchApiKeys(), fetchServiceAccounts(), fetchRateLimitStatus().catch(() => null as any)]);
      setKeys(k);
      setSas(s);
      if (r) setRl(r);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load API keys"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreateKey = async () => {
    setError(null);
    try {
      const res = await createApiKey({ name: newKeyName, scopes: newKeyScopes, expires_days: newKeyExpiry, service_account_id: newKeySaId });
      setLastCreatedRaw(res.raw_key);
      showSuccess(`API key ${res.name} created — copy now`);
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to create API key"));
    }
  };

  const handleRevokeKey = async (id: number) => {
    if (!confirm("Revoke this API key? Clients using it will stop working immediately.")) return;
    try {
      await revokeApiKey(id);
      showSuccess("API key revoked");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to revoke API key"));
    }
  };

  const handleCreateSa = async () => {
    setError(null);
    try {
      await createServiceAccount({ name: newSaName, description: newSaDesc, role: newSaRole });
      showSuccess(`Service account ${newSaName} created`);
      setNewSaName("");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to create service account"));
    }
  };

  const handleRevokeSa = async (id: number) => {
    if (!confirm("Revoke this service account? All its API keys will also be revoked and user deactivated.")) return;
    try {
      await revokeServiceAccount(id);
      showSuccess("Service account revoked");
      await load();
    } catch (err: any) {
      setError(getApiError(err, "Failed to revoke service account"));
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader title="API Keys & Service Accounts" description="Phase 47: Multi-tenant org isolation, API keys (sk_ prefix, hashed at rest), service accounts, per-org rate limiting (Redis optional)." />
        <p className="text-sm text-content-tertiary">Loading…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="API Keys & Service Accounts" description="Multi-tenant org isolation (org_id filter on every query), API keys with scopes (hashed at rest, prefix lookup), service accounts (User is_service_account=True), per-org rate limiting (Redis sliding window, memory fallback)." />

      {error && <div role="alert" className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">{error}</div>}

      {lastCreatedRaw && (
        <div className="px-4 py-3 rounded-lg bg-status-warning/10 border border-status-warning/30 text-sm">
          <p className="font-semibold text-content-primary">Copy this API key now — it will not be shown again:</p>
          <code className="mt-2 block p-2 bg-app-subtle rounded text-xs break-all font-mono">{lastCreatedRaw}</code>
          <p className="mt-2 text-xs text-content-tertiary">Use as X-API-Key header: X-API-Key: {lastCreatedRaw.slice(0, 20)}… — org isolation enforced, scopes intersect role perms, rate limited per-org.</p>
          <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLastCreatedRaw(null)}>Dismiss</Button>
        </div>
      )}

      {rl && (
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-2">Per-Org Rate Limit Status</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div><span className="text-content-tertiary">Backend:</span> <span className="font-mono font-semibold">{rl.backend}</span></div>
            <div><span className="text-content-tertiary">Enabled:</span> <span className="font-semibold">{String(rl.enabled)}</span></div>
            <div><span className="text-content-tertiary">RPS Limit:</span> <span className="font-mono">{rl.rps_limit}</span> burst <span className="font-mono">{rl.burst_limit}</span></div>
            <div><span className="text-content-tertiary">Current:</span> <span className="font-mono">{rl.current_rps} req/s</span>, <span className="font-mono">{rl.current_per_minute}/min</span></div>
          </div>
          <p className="text-[11px] text-content-tertiary mt-2">Redis if REDIS_URL set, else in-memory deque per org (process-local, N workers × limit). Enforced on every authenticated request via check_org_rate_limit.</p>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* API Keys */}
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-1">API Keys — sk_{"{prefix}"}_{"{secret}"} (hashed at rest)</h3>
          <p className="text-xs text-content-tertiary mb-4">Org-scoped, prefix for lookup, bcrypt hash of secret, last4 for UI, scopes intersect role perms, expires_at optional, last_used_at updated on verify.</p>

          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input className="px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="Key name" />
              <input className="px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={newKeyScopes} onChange={(e) => setNewKeyScopes(e.target.value)} placeholder="scopes e.g. alerts:read,alerts:write or *" />
            </div>
            <div className="flex gap-2">
              <input className="w-24 px-2 py-1 rounded bg-app-subtle border border-line-subtle text-xs" type="number" value={newKeyExpiry || ""} onChange={(e) => setNewKeyExpiry(e.target.value ? parseInt(e.target.value) : undefined)} placeholder="expiry days" />
              <select value={newKeySaId || ""} onChange={(e) => setNewKeySaId(e.target.value ? parseInt(e.target.value) : undefined)} className="flex-1 px-2 py-1 rounded bg-app-subtle border border-line-subtle text-xs">
                <option value="">No service account (creator user)</option>
                {sas.filter(s => s.is_active).map(sa => <option key={sa.id} value={sa.id}>{sa.name} ({sa.username})</option>)}
              </select>
              <Button variant="secondary" size="sm" onClick={handleCreateKey}>Create Key</Button>
            </div>

            <div className="space-y-2 pt-2">
              {keys.length === 0 ? <p className="text-xs text-content-tertiary">No API keys — create one for CI/CD or automation.</p> :
                keys.map(k => (
                  <div key={k.id} className="flex items-center justify-between p-2 rounded-lg bg-app-subtle border border-line-subtle">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-content-primary truncate">{k.name} <span className="font-mono text-[10px] text-content-tertiary">{k.prefix}…{k.last4}</span> {k.is_active ? <span className="text-status-success">● active</span> : <span className="text-status-critical">● revoked</span>}</p>
                      <p className="text-[10px] text-content-tertiary">scopes: {k.scopes} · created {k.created_at ? new Date(k.created_at).toLocaleDateString() : "—"} {k.last_used_at ? `· last used ${new Date(k.last_used_at).toLocaleDateString()}` : "· never used"}</p>
                    </div>
                    {k.is_active && <Button variant="ghost" size="sm" onClick={() => handleRevokeKey(k.id)}>Revoke</Button>}
                  </div>
                ))}
            </div>
          </div>
        </Card>

        {/* Service Accounts */}
        <Card padded>
          <h3 className="text-sm font-bold text-content-primary mb-1">Service Accounts — machine identity</h3>
          <p className="text-xs text-content-tertiary mb-4">Creates User with is_service_account=True + ServiceAccount wrapper. Role SERVICE has alert read/write/export, analytics read, engine read, etc. Revoking SA deactivates user + revokes all its API keys.</p>

          <div className="space-y-3">
            <div className="flex gap-2">
              <input className="flex-1 px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={newSaName} onChange={(e) => setNewSaName(e.target.value)} placeholder="Service account name e.g. automation-bot" />
              <select value={newSaRole} onChange={(e) => setNewSaRole(e.target.value)} className="px-2 py-1 rounded bg-app-subtle border border-line-subtle text-xs">
                <option value="service">service</option>
                <option value="service_readonly">service_readonly</option>
                <option value="ANALYST">ANALYST</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>
            <input className="w-full px-3 py-2 rounded-lg bg-app-subtle border border-line-subtle text-sm" value={newSaDesc} onChange={(e) => setNewSaDesc(e.target.value)} placeholder="Description" />
            <Button variant="secondary" size="sm" onClick={handleCreateSa}>Create Service Account</Button>

            <div className="space-y-2 pt-2">
              {sas.length === 0 ? <p className="text-xs text-content-tertiary">No service accounts — create one for machine-to-machine auth.</p> :
                sas.map(sa => (
                  <div key={sa.id} className="flex items-center justify-between p-2 rounded-lg bg-app-subtle border border-line-subtle">
                    <div>
                      <p className="text-xs font-semibold text-content-primary">{sa.name} <span className="font-mono text-[10px] text-content-tertiary">{sa.username}</span> {sa.is_active ? <span className="text-status-success">● active</span> : <span className="text-status-critical">● revoked</span>}</p>
                      <p className="text-[10px] text-content-tertiary">{sa.description || "—"} · role {sa.role} · created {sa.created_at ? new Date(sa.created_at).toLocaleDateString() : "—"}</p>
                    </div>
                    {sa.is_active && <Button variant="ghost" size="sm" onClick={() => handleRevokeSa(sa.id)}>Revoke</Button>}
                  </div>
                ))}
            </div>

            <div className="pt-3 border-t border-line-subtle space-y-1">
              <p className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">Org Isolation Notes</p>
              <p className="text-[11px] text-content-secondary">Every query filters by org_id (ApiKey.org_id, ServiceAccount.org_id, User.org_id). JWT and API key auth both resolve org_id and enforce via check_org_rate_limit + ABAC scope intersection. No cross-tenant read possible — verified by org_id in WHERE clause.</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
