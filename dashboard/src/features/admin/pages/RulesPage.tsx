import React, { useCallback, useEffect, useState } from "react";
import RulesApi, { DetectionRule } from "../../../api/rulesApi";
import {
  PageHeader,
  SkeletonTable,
  EmptyState,
  Card,
  Modal,
  ConfirmDialog,
  SeverityBadge,
  Select,
  StatusBadge,
} from "../../../components/ui";
import TextInput from "../../../components/common/TextInput";
import { showSuccess } from "../../../utils/showSuccess";
import { showError } from "../../../utils/showError";
import { ShieldCheck } from "lucide-react";
import { getApiError } from "../../../utils/getApiError";

interface RuleForm {
  name: string;
  description: string;
  severity: string;
  pattern: string;
}

const EMPTY_FORM: RuleForm = { name: "", description: "", severity: "MEDIUM", pattern: "" };

const RulesPage: React.FC = () => {
  const [rules, setRules] = useState<DetectionRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DetectionRule | null>(null);
  const [form, setForm] = useState<RuleForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DetectionRule | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await RulesApi.fetchRules();
      setRules(res.data);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load detection rules"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setModalOpen(true);
  };

  const openEdit = (rule: DetectionRule) => {
    setEditing(rule);
    setForm({
      name: rule.name,
      description: rule.description || "",
      severity: rule.severity,
      pattern: rule.pattern || "",
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      showError("Rule name is required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        severity: form.severity,
        pattern: form.pattern.trim() || undefined,
      };
      if (editing) {
        await RulesApi.updateRule(editing.id, payload);
        showSuccess("Rule updated");
      } else {
        await RulesApi.createRule(payload);
        showSuccess("Rule created");
      }
      setModalOpen(false);
      load();
    } catch (err: any) {
      showError(getApiError(err, "Failed to save rule"));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (rule: DetectionRule) => {
    try {
      await RulesApi.updateRule(rule.id, { is_active: !rule.is_active });
      showSuccess(rule.is_active ? "Rule deactivated" : "Rule activated");
      load();
    } catch (err: any) {
      showError(getApiError(err, "Failed to toggle rule"));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await RulesApi.deleteRule(deleteTarget.id);
      showSuccess("Rule deleted");
      setDeleteTarget(null);
      load();
    } catch (err: any) {
      showError(getApiError(err, "Failed to delete rule"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Detection Rules"
        description="Tunable signatures and heuristics used by the detection engine. Changes are audited."
        backTo="/admin"
        crumbs={[{ label: "Admin", to: "/admin" }, { label: "Detection Rules" }]}
        actions={
          <button
            type="button"
            onClick={openCreate}
            className="px-4 py-2 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition shadow-md"
          >
            + New Rule
          </button>
        }
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonTable rows={6} cols={4} />
      ) : rules.length === 0 ? (
        <Card className="p-6">
          <EmptyState
            icon={<ShieldCheck size={28} />}
            title="No detection rules yet"
            description="Create a signature or heuristic rule to tune the engine."
            action={
              <button
                type="button"
                onClick={openCreate}
                className="px-4 py-2 rounded-lg bg-accent-primary text-brand-ink text-sm font-semibold hover:opacity-90 transition"
              >
                Create rule
              </button>
            }
          />
        </Card>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-app-subtle border-b border-line-subtle text-xs font-semibold uppercase tracking-wider text-content-secondary">
              <tr>
                <th scope="col" className="px-5 py-3">Name</th>
                <th scope="col" className="px-5 py-3">Severity</th>
                <th scope="col" className="px-5 py-3">Pattern</th>
                <th scope="col" className="px-5 py-3">Status</th>
                <th scope="col" className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-subtle text-sm">
              {rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-app-subtle/50 transition">
                  <td className="px-5 py-3">
                    <p className="text-content-primary font-medium">{rule.name}</p>
                    {rule.description && (
                      <p className="text-xs text-content-tertiary mt-0.5 max-w-md truncate" title={rule.description}>
                        {rule.description}
                      </p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <SeverityBadge severity={rule.severity} />
                  </td>
                  <td className="px-5 py-3 font-mono text-xs text-accent-primary max-w-xs truncate" title={rule.pattern || ""}>
                    {rule.pattern || "—"}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge tone={rule.is_active ? "success" : "neutral"} label={rule.is_active ? "Active" : "Inactive"} />
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => toggleActive(rule)}
                        className="px-2.5 py-1 text-xs rounded-md bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary transition"
                      >
                        {rule.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        type="button"
                        onClick={() => openEdit(rule)}
                        className="px-2.5 py-1 text-xs rounded-md bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-primary transition"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(rule)}
                        className="px-2.5 py-1 text-xs rounded-md bg-status-critical/15 hover:bg-status-critical/25 border border-status-critical/30 text-status-critical transition"
                      >
                        Delete
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
        title={editing ? "Edit Detection Rule" : "New Detection Rule"}
        description="Rules are matched against incoming logs to surface detections."
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
              {saving ? "Saving…" : editing ? "Save Changes" : "Create Rule"}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <TextInput
            name="name"
            label="Rule Name"
            placeholder="e.g. RDP brute-force"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <TextInput
            name="description"
            label="Description"
            placeholder="What this rule detects"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
          <Select
            id="severity"
            label="Severity"
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
            options={[
              { value: "CRITICAL", label: "Critical" },
              { value: "HIGH", label: "High" },
              { value: "MEDIUM", label: "Medium" },
              { value: "LOW", label: "Low" },
            ]}
          />
          <TextInput
            name="pattern"
            label="Pattern (regex / signature)"
            placeholder="e.g. Failed password for .* from"
            value={form.pattern}
            onChange={(e) => setForm((f) => ({ ...f, pattern: e.target.value }))}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete detection rule"
        message={
          <>
            Delete <strong className="text-content-primary">{deleteTarget?.name}</strong>? This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export default RulesPage;