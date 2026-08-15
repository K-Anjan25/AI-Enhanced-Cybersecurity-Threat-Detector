import React, { useEffect, useState } from "react";
import EngineApi from "../../api/engineApi";
import type { EngineSettings } from "../../types/engine";
import { BackButton } from "../../components/ui";

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

  const cardCls = "bg-app-surface border border-line-subtle rounded-xl p-5 shadow-sm";

  return (
    <div className="space-y-6">
      <header>
        <div className="mb-1.5">
          <BackButton to="/admin" label="Back to Admin" />
        </div>
        <h1 className="text-2xl font-semibold text-content-primary">Engine Settings</h1>
        <p className="text-sm text-content-secondary mt-1">
          Configure the AI threat detection engine. Changes are persisted and audited.
        </p>
      </header>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
          {error}
        </div>
      )}
      {success && (
        <div className="px-4 py-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-status-success">
          {success}
        </div>
      )}

      {loading ? (
        <div className="p-6 bg-app-surface border border-line-subtle rounded-xl text-sm text-content-tertiary">
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
              <div className="flex gap-2">
                {(["LOW", "MEDIUM", "HIGH"] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => update({ detectionSensitivity: level })}
                    className={`flex-1 px-3 py-2 rounded-lg text-sm font-semibold border transition ${
                      settings.detectionSensitivity === level
                        ? "bg-accent-primary/10 border-accent-primary text-accent-primary"
                        : "bg-app-bg border-line-subtle text-content-secondary hover:bg-app-subtle"
                    }`}
                  >
                    {level}
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
              <input
                id="maxScans"
                type="number"
                min={1}
                max={100}
                value={settings.maxConcurrentScans}
                onChange={(e) => update({ maxConcurrentScans: Number(e.target.value) })}
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary"
              />
            </div>

            <div className={cardCls}>
              <label htmlFor="retention" className="text-sm font-semibold text-content-secondary">
                Log Retention (days)
              </label>
              <p className="text-xs text-content-tertiary mt-1 mb-3">
                How long processed log history is retained before purging.
              </p>
              <input
                id="retention"
                type="number"
                min={1}
                max={3650}
                value={settings.logRetentionDays}
                onChange={(e) => update({ logRetentionDays: Number(e.target.value) })}
                className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary"
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
              className="px-6 py-2.5 rounded-lg bg-accent-primary text-app-bg text-sm font-semibold hover:bg-accent-secondary transition disabled:opacity-50"
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
