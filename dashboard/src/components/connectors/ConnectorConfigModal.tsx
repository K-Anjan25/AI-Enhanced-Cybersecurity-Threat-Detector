import React, { useEffect, useState } from "react";
import { Copy, Check } from "lucide-react";
import { Modal, Button, Spinner } from "../ui";
import { Select } from "../ui/Select";
import ConnectorApi from "../../api/connectorApi";
import type {
  Connector,
  ConnectorConfig,
  ConnectorConfigInput,
} from "../../types/analyst";
import { getApiError } from "../../utils/getApiError";

interface Props {
  open: boolean;
  connector: Connector | null;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Configure how a connector actually delivers events.
 *
 * Two honest modes:
 *  - **push** — the source POSTs to our webhook with a shared secret. Works
 *    with nothing more than a cron job and curl; no vendor account needed.
 *  - **poll** — NOCTRA fetches the endpoint on demand. Requires a URL.
 *
 * The outbound credential is write-only: we show whether one is set, never its
 * value, and the field is left blank to change it.
 */
const ConnectorConfigModal: React.FC<Props> = ({ open, connector, onClose, onSaved }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<ConnectorConfig | null>(null);
  const [mode, setMode] = useState<"poll" | "push">("push");
  const [endpoint, setEndpoint] = useState("");
  const [authHeader, setAuthHeader] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [ingestToken, setIngestToken] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open || !connector) return;
    let alive = true;
    setError(null);
    setCopied(false);
    setLoading(true);
    ConnectorApi.fetchConfig(connector.id)
      .then((cfg) => {
        if (!alive) return;
        setConfig(cfg);
        setMode(cfg.mode);
        setEndpoint(cfg.endpoint ?? "");
        setAuthHeader(cfg.auth_header ?? "");
        setAuthToken("");
        setIngestToken("");
        setEnabled(cfg.enabled);
      })
      .catch(() => {
        // No configuration yet — that is the normal first-run state.
        if (!alive) return;
        setConfig(null);
        setMode("push");
        setEndpoint("");
        setAuthHeader("");
        setAuthToken("");
        setIngestToken("");
        setEnabled(true);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [open, connector]);

  if (!connector) return null;

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      const payload: ConnectorConfigInput = { mode, enabled };
      if (endpoint.trim()) payload.endpoint = endpoint.trim();
      if (authHeader.trim()) payload.auth_header = authHeader.trim();
      // Only send secrets when the operator typed a new one — a blank field
      // must never wipe a stored credential.
      if (authToken) payload.auth_token = authToken;
      if (ingestToken) payload.ingest_token = ingestToken;
      await ConnectorApi.saveConfig(connector.id, payload);
      onSaved();
      onClose();
    } catch (err: any) {
      setError(getApiError(err, "Could not save the connector configuration."));
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    setError(null);
    setSaving(true);
    try {
      await ConnectorApi.deleteConfig(connector.id);
      onSaved();
      onClose();
    } catch (err: any) {
      setError(getApiError(err, "Could not remove the connector configuration."));
    } finally {
      setSaving(false);
    }
  };

  const hook = ConnectorApi.webhookUrl(connector.id);
  const [oauthStatus, setOauthStatus] = useState<{ connected: boolean; account_name?: string } | null>(null);

  useEffect(() => {
    if (!open || !connector) return;
    if (connector.id === "github" || connector.id === "slack") {
      ConnectorApi.fetchOAuthStatus(connector.id)
        .then(setOauthStatus)
        .catch(() => setOauthStatus({ connected: false }));
    } else {
      setOauthStatus(null);
    }
  }, [open, connector]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Copy failed — select the text and copy manually.");
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Configure ${connector.name}`}
      description="How this source delivers events to NOCTRA. Nothing is fetched until a source is configured and enabled."
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-3 w-full">
          {config ? (
            <Button variant="secondary" onClick={handleRemove} disabled={saving}>
              Remove
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? <Spinner variant="light" label="Saving" /> : "Save configuration"}
            </Button>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className="py-8 flex justify-center text-content-secondary text-sm">
          <Spinner label="Loading configuration" />
        </div>
      ) : (
        <div className="space-y-4">
          {error && (
            <p role="alert" className="text-xs text-status-critical">
              {error}
            </p>
          )}

          <div>
            <label className="tech-label text-content-tertiary block mb-1.5" htmlFor="conn-mode">
              Delivery mode
            </label>
            <Select
              id="conn-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as "poll" | "push")}
              options={[
                { value: "push", label: "Push — source posts to our webhook" },
                { value: "poll", label: "Poll — NOCTRA fetches an endpoint" },
              ]}
            />
          </div>

          {mode === "poll" ? (
            <>
              <div>
                <label
                  className="tech-label text-content-tertiary block mb-1.5"
                  htmlFor="conn-endpoint"
                >
                  Events endpoint
                </label>
                <input
                  id="conn-endpoint"
                  type="url"
                  value={endpoint}
                  onChange={(e) => setEndpoint(e.target.value)}
                  placeholder="https://provider.example/events"
                  className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary font-mono"
                />
                <p className="text-[11px] text-content-tertiary mt-1">
                  Expected to return a JSON array of events, or an object with an
                  <code className="font-mono"> events</code> key.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label
                    className="tech-label text-content-tertiary block mb-1.5"
                    htmlFor="conn-auth-header"
                  >
                    Auth header
                  </label>
                  <input
                    id="conn-auth-header"
                    value={authHeader}
                    onChange={(e) => setAuthHeader(e.target.value)}
                    placeholder="Authorization"
                    className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary font-mono"
                  />
                </div>
                <div>
                  <label
                    className="tech-label text-content-tertiary block mb-1.5"
                    htmlFor="conn-auth-token"
                  >
                    Auth token
                  </label>
                  <input
                    id="conn-auth-token"
                    type="password"
                    value={authToken}
                    onChange={(e) => setAuthToken(e.target.value)}
                    placeholder={config?.has_auth_token ? "Stored — leave blank to keep" : "Bearer …"}
                    className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary font-mono"
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-3">
              <div>
                <label
                  className="tech-label text-content-tertiary block mb-1.5"
                  htmlFor="conn-ingest-token"
                >
                  Shared secret (sent as X-Connector-Token)
                </label>
                <input
                  id="conn-ingest-token"
                  type="password"
                  value={ingestToken}
                  onChange={(e) => setIngestToken(e.target.value)}
                  placeholder={config?.has_ingest_token ? "Stored — leave blank to keep" : "choose a long random string"}
                  className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary font-mono"
                />
              </div>

              <div className="console-panel rounded-sm p-3">
                <p className="tech-label text-content-tertiary mb-1.5">Webhook</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-[11px] text-content-primary font-mono break-all">
                    POST {hook}
                  </code>
                  <button
                    type="button"
                    onClick={() => copy(hook)}
                    className="shrink-0 p-1.5 rounded-sm border border-line-subtle text-content-secondary hover:text-accent-primary hover:border-accent-primary transition-colors"
                    aria-label="Copy webhook URL"
                  >
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                </div>
                <p className="text-[11px] text-content-tertiary mt-2">
                  Body: <code className="font-mono">{"{ \"events\": [{ \"message\": \"…\", \"severity\": \"HIGH\" }] }"}</code>
                </p>
              </div>
            </div>
          )}

          {(connector.id === "github" || connector.id === "slack") && (
            <div className="console-panel rounded-sm p-3">
              <p className="tech-label text-content-tertiary mb-1.5">OAuth — {connector.id === "github" ? "GitHub App" : "Slack"}</p>
              {oauthStatus?.connected ? (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-content-secondary">
                    Connected as <span className="font-semibold text-content-primary">{oauthStatus.account_name || "authorized account"}</span> — polling will use OAuth token automatically.
                  </p>
                  <Button variant="ghost" size="sm" onClick={async () => {
                    try {
                      await ConnectorApi.disconnectOAuth(connector.id);
                      setOauthStatus({ connected: false });
                    } catch (err: any) {
                      setError(getApiError(err, "Failed to disconnect OAuth"));
                    }
                  }}>Disconnect</Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-[11px] text-content-tertiary">Connect via OAuth to ingest directly from {connector.id === "github" ? "GitHub Advanced Security" : "Slack Audit Logs"} API. Token encrypted at rest.</p>
                  <a href={ConnectorApi.oauthStartUrl(connector.id)} className="inline-flex items-center px-3 py-1.5 rounded-sm bg-app-surface border border-line-subtle text-xs font-semibold text-accent-primary hover:border-accent-primary transition-colors">
                    Connect {connector.id === "github" ? "GitHub" : "Slack"} via OAuth
                  </a>
                </div>
              )}
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-content-secondary">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="accent-accent-primary"
            />
            Enabled
          </label>

          {connector.events_ingested != null && connector.events_ingested > 0 && (
            <p className="text-[11px] text-content-tertiary">
              {connector.events_ingested} event
              {connector.events_ingested === 1 ? "" : "s"} ingested from this source so far.
            </p>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ConnectorConfigModal;
