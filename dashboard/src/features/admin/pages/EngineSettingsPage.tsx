import React, { useEffect, useState } from "react";
import EngineApi from "../../../api/engineApi";
import type { EngineSettings } from "../../../types/engine";
import { NumberInput, PageHeader } from "../../../components/ui";

const DEFAULT_SETTINGS: EngineSettings = {
  detectionSensitivity: "MEDIUM",
  maxConcurrentScans: 10,
  autoQuarantine: false,
  kafkaEnabled: false,
  logRetentionDays: 30,
};

const EngineSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<EngineSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    EngineApi.getEngineSettings()
      .then((data) => {
        if (!cancelled) {
          setSettings(data);
          setError(null);
        }
      })
      .catch((err: any) => {
        if (!cancelled) setError(typeof err === "string" ? err : "Failed to load engine settings");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = (patch: Partial<EngineSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await EngineApi.updateEngineSettings(settings);
      setSettings(result.settings);
      setSuccess(result.message || "Engine settings saved successfully");
    } catch (err: any) {
      const detail = err?.detail || (typeof err === "string" ? err : "Failed to save engine settings");
      setError(detail);
    } finally {
      setSaving(false);
    }
  };

  const cardCls = "bg-app-surface border border-line-subtle rounded-2xl p-5 shadow-card";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Engine Settings"
        backTo="/admin"
        crumbs={[{ label: "Administration", to: "/admin" }, { label: "Engine Settings" }]}
        description="Configure the AI threat detection engine. Changes are persisted and audited."
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}
      {success && (
        <div className="px-4 py-3 rounded-lg bg-status-success/10 border border-status-success/30 text-sm text-status-success">
          {success}
        </div>
      )}

      {loading ? (
        <div className="p-6 bg-app-surface border border-line-subtle rounded-2xl text-sm text-content-tertiary">
          Loading engine settings...
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className={cardCls}>
              <label className="text-sm font-semibold text-content-secondary">Detection Sensitivity</label>
              <p className="text-xs text-content-tertiary mt-1 mb-3">
                Higher sensitivity flags more events as suspicious, increasing false positives.
              </p>
              <div className="flex gap-1 p-1 rounded-full bg-app-subtle border border-line-subtle w-fit">
                {(["LOW", "MEDIUM", "HIGH"] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => update({ detectionSensitivity: level })}
                    className={`px-4 py-1.5 rounded-full text-xs font-semibold transition ${
                      settings.detectionSensitivity === level
                        ? "bg-brand-gradient text-brand-ink shadow-float"
                        : "text-content-secondary hover:text-content-primary"
                    }`}
                  >
                    {level.charAt(0) + level.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className={cardCls}>
              <label htmlFor="maxScans" className="text-sm font-semibold text-content-secondary">
                Max Concurrent Scans
              </label>
              <p className="text-xs text-content-tertiary mt-1 mb-3">
                Maximum parallel scan workers the engine may spawn.
              </p>
              <NumberInput
                id="maxScans"
                min={1}
                max={100}
                value={settings.maxConcurrentScans}
                onChange={(v) => update({ maxConcurrentScans: Number.isNaN(v) ? 1 : v })}
              />
            </div>

            <div className={cardCls}>
              <label htmlFor="retention" className="text-sm font-semibold text-content-secondary">
                Log Retention (days)
              </label>
              <p className="text-xs text-content-tertiary mt-1 mb-3">
                How long processed log history is retained before purging.
              </p>
              <NumberInput
                id="retention"
                min={1}
                max={3650}
                value={settings.logRetentionDays}
                onChange={(v) => update({ logRetentionDays: Number.isNaN(v) ? 1 : v })}
              />
            </div>

            <div className={cardCls}>
              <span className="text-sm font-semibold text-content-secondary">Automated Mitigation</span>
              <p className="text-xs text-content-tertiary mt-1 mb-3">
                Toggle engine capabilities. Changes apply to newly processed traffic.
              </p>
              <div className="space-y-3">
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-sm text-content-primary">Auto-quarantine threats</span>
                  <input
                    type="checkbox"
                    checked={settings.autoQuarantine}
                    onChange={(e) => update({ autoQuarantine: e.target.checked })}
                    className="w-4 h-4 rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
                  />
                </label>
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-sm text-content-primary">Stream alerts via Kafka</span>
                  <input
                    type="checkbox"
                    checked={settings.kafkaEnabled}
                    onChange={(e) => update({ kafkaEnabled: e.target.checked })}
                    className="w-4 h-4 rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
                  />
                </label>
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-6 py-2.5 rounded-full bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default EngineSettingsPage;
