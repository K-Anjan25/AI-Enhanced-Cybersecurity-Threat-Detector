import React from "react";
import type { CreateIncidentPayload, Incident } from "../../../types/incident";
import Button from "../../../components/ui/Button";

interface Props {
  onClose: () => void;
  onSubmit: (payload: CreateIncidentPayload) => Promise<void>;
  submitting: boolean;
  sourceAlertId?: number | null;
}

const CreateIncidentModal: React.FC<Props> = ({
  onClose,
  onSubmit,
  submitting,
  sourceAlertId,
}) => {
  const [title, setTitle] = React.useState<string>("");
  const [description, setDescription] = React.useState<string>("");
  const [priority, setPriority] = React.useState<string>("medium");
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError("A title is required.");
      return;
    }
    try {
      await onSubmit({
        title: title.trim(),
        description: description.trim() || undefined,
        priority: priority as CreateIncidentPayload["priority"],
        source_alert_id: sourceAlertId ?? undefined,
      });
    } catch (err: any) {
      setError(err?.detail || "Failed to open incident. Please try again.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-app-surface w-full max-w-lg rounded-xl p-6 shadow-2xl border border-line-subtle max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-5">
          <h3 className="text-lg font-semibold text-content-primary">New incident</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-content-tertiary hover:text-content-primary text-xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="incident-title" className="block text-sm font-medium text-content-secondary mb-1.5">
              Title
            </label>
            <input
              id="incident-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Brute-force campaign against SSH bastion"
              className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition"
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="incident-description" className="block text-sm font-medium text-content-secondary mb-1.5">
              Description <span className="text-content-tertiary">(optional)</span>
            </label>
            <textarea
              id="incident-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Context for the investigating analyst..."
              className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary transition resize-none"
            />
          </div>

          <div>
            <label htmlFor="incident-priority" className="block text-sm font-medium text-content-secondary mb-1.5">
              Priority
            </label>
            <select
              id="incident-priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full bg-app-bg border border-line-subtle rounded-lg px-3.5 py-2 text-sm text-content-primary focus:outline-none focus:border-accent-primary transition cursor-pointer"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          {error && (
            <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2.5 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Opening..." : "Open incident"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateIncidentModal;