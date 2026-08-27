import React, { useCallback, useEffect, useState } from "react";
import ReputationApi, { IpReputationEntry } from "../../api/reputationApi";
import {
  PageHeader,
  SkeletonTable,
  EmptyState,
  Card,
  Modal,
  StatusBadge,
  Select,
} from "../../components/ui";
import TextInput from "../../components/common/TextInput";
import { showSuccess } from "../../utils/showSuccess";
import { showError } from "../../utils/showError";
import { ShieldOff } from "lucide-react";
import { getApiError } from "../../utils/getApiError";

interface ReputationForm {
  ip_address: string;
  threat_score: string;
  category: string;
  notes: string;
  is_blocked: boolean;
}

const EMPTY_FORM: ReputationForm = {
  ip_address: "",
  threat_score: "0",
  category: "manual",
  notes: "",
  is_blocked: false,
};

const scoreTone = (score: number): "critical" | "warning" | "neutral" =>
  score >= 0.75 ? "critical" : score >= 0.4 ? "warning" : "neutral";

const scoreColor = (score: number): string => {
  if (score >= 0.75) return "bg-status-critical/15 text-status-critical border-status-critical/30";
  if (score >= 0.4) return "bg-status-warning/15 text-status-warning border-status-warning/30";
  return "bg-app-subtle text-content-secondary border-line-subtle";
};

const ReputationPage: React.FC = () => {
  const [rows, setRows] = useState<IpReputationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<ReputationForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [blocking, setBlocking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await ReputationApi.fetchReputation();
      setRows(res.data);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load IP reputation"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const handleSave = async () => {
    const ip = form.ip_address.trim();
    if (!ip) {
      showError("IP address is required");
      return;
    }
    setSaving(true);
    try {
      await ReputationApi.upsertReputation({
        ip_address: ip,
        threat_score: Math.min(1, Math.max(0, Number(form.threat_score) || 0)),
        is_blocked: form.is_blocked,
        category: form.category.trim() || "manual",
        notes: form.notes.trim() || undefined,
      });
      showSuccess("Reputation entry saved");
      setModalOpen(false);
      load();
    } catch (err: any) {
      showError(getApiError(err, "Failed to save reputation entry"));
    } finally {
      setSaving(false);
    }
  };

  const toggleBlock = async (entry: IpReputationEntry) => {
    setBlocking(entry.ip_address);
    try {
      if (entry.is_blocked) {
        await ReputationApi.unblockIp(entry.ip_address);
        showSuccess(`${entry.ip_address} unblocked`);
      } else {
        await ReputationApi.blockIp(entry.ip_address);
        showSuccess(`${entry.ip_address} blocked`);
      }
      load();
    } catch (err: any) {
      showError(getApiError(err, "Failed to update block status"));
    } finally {
      setBlocking(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="IP Reputation"
        description="Threat-intel scoring and blacklist status for observed source IPs. Changes are audited."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "IP Reputation" }]}
        actions={
          <button
            type="button"
            onClick={openCreate}
            className="px-4 py-2 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition shadow-md"
          >
            + Add IP
          </button>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={6} cols={5} />
      ) : rows.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={<ShieldOff size={28} />}
            title="No reputation entries yet"
            description="Add an IP with a threat score, or block addresses from the alerts view."
            action={
              <button
                type="button"
                onClick={openCreate}
                className="px-4 py-2 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition"
              >
                Add IP
              </button>
            }
          />
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
              <tr>
                <th className="px-5 py-3">IP Address</th>
                <th className="px-5 py-3">Threat Score</th>
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
              {rows.map((row) => (
                <tr key={row.id ?? row.ip_address} className="hover:bg-app-subtle/50 transition">
                  <td className="px-5 py-3">
                    <span className="font-mono text-content-primary">{row.ip_address}</span>
                    {row.notes && (
                      <p className="text-xs text-content-tertiary mt-0.5 max-w-xs truncate" title={row.notes}>
                        {row.notes}
                      </p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border tabular-nums ${scoreColor(row.threat_score)}`}>
                      {(row.threat_score * 100).toFixed(0)}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-content-secondary">{row.category || "—"}</td>
                  <td className="px-5 py-3">
                    <StatusBadge tone={row.is_blocked ? "critical" : "success"} label={row.is_blocked ? "Blocked" : "Clear"} />
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={() => toggleBlock(row)}
                        disabled={blocking === row.ip_address}
                        className={`px-2.5 py-1 text-xs rounded-md border transition disabled:opacity-50 ${
                          row.is_blocked
                            ? "bg-app-subtle hover:bg-line-bright border-line-subtle text-content-secondary"
                            : "bg-status-critical/15 hover:bg-status-critical/25 border-status-critical/30 text-status-critical"
                        }`}
                      >
                        {blocking === row.ip_address ? "…" : row.is_blocked ? "Unblock" : "Block"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Add / Update IP Reputation"
        description="Manually score or blacklist a source address."
        footer={
          <>
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="px-4 py-2 text-sm rounded-lg text-content-secondary hover:bg-app-subtle transition"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-accent-primary text-brand-ink hover:opacity-90 transition disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save Entry"}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <TextInput
            name="ip_address"
            label="IP Address"
            placeholder="e.g. 203.0.113.9"
            value={form.ip_address}
            onChange={(e) => setForm((f) => ({ ...f, ip_address: e.target.value }))}
          />
          <TextInput
            name="threat_score"
            label="Threat Score (0 – 1)"
            placeholder="e.g. 0.85"
            value={form.threat_score}
            onChange={(e) => setForm((f) => ({ ...f, threat_score: e.target.value }))}
          />
          <Select
            id="category"
            label="Category"
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            options={[
              { value: "manual", label: "Manual review" },
              { value: "scanner", label: "Port scanner" },
              { value: "botnet", label: "Botnet / C2" },
              { value: "phishing", label: "Phishing source" },
              { value: "admin_blocked", label: "Admin blocked" },
            ]}
          />
          <TextInput
            name="notes"
            label="Notes"
            placeholder="Optional context"
            value={form.notes}
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
          />
          <label className="flex items-center justify-between cursor-pointer pt-1">
            <span className="text-sm text-content-primary">Block this IP immediately</span>
            <input
              type="checkbox"
              checked={form.is_blocked}
              onChange={(e) => setForm((f) => ({ ...f, is_blocked: e.target.checked }))}
              className="w-4 h-4 rounded border-line-subtle bg-app-bg text-accent-primary focus:ring-0"
            />
          </label>
        </div>
      </Modal>
    </div>
  );
};

export default ReputationPage;