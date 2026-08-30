import React, { useCallback, useEffect, useState } from "react";
import { Archive, Gavel, Play, Plus } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Modal,
  PageHeader,
  SkeletonCard,
  Badge,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Data retention — how long each kind of record is kept, and what gets archived.
 *
 * This is also the "recover" input to the posture score: a tenant with no active
 * retention policy scores 20 there, because unbounded retention with no archive
 * is a genuine resilience gap rather than missing data.
 */

interface Policy {
  id: number;
  data_type: string;
  retention_days: number;
  archive_after_days?: number | null;
  delete_after_days?: number | null;
  is_active: boolean;
}

/** Matches GET /data-lifecycle/legal-holds. The earlier `reason`/`data_type`
 *  fields never existed on the response, so a hold's detail always rendered
 *  blank. */
interface LegalHold {
  id: number;
  name?: string | null;
  description?: string | null;
  case_ids?: number[] | null;
  is_active?: boolean;
  created_at?: string | null;
}

const asList = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

export default function DataRetentionPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [holds, setHolds] = useState<LegalHold[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [confirmRelease, setConfirmRelease] = useState<LegalHold | null>(null);
  const [holdOpen, setHoldOpen] = useState(false);
  const [holdName, setHoldName] = useState("");
  const [holdDescription, setHoldDescription] = useState("");
  const { push } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const [p, h] = await Promise.allSettled([
      apiClient.get("/data-lifecycle/policies"),
      apiClient.get("/data-lifecycle/legal-holds"),
    ]);
    if (p.status === "fulfilled") setPolicies(asList<Policy>(p.value.data));
    if (h.status === "fulfilled") setHolds(asList<LegalHold>(h.value.data));
    if (p.status === "rejected") push(getApiError(p.reason, "Could not load policies"), "error");
    setLoading(false);
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const runAutomation = async () => {
    setConfirmRun(false);
    setBusy(true);
    try {
      const res = await apiClient.post("/data-lifecycle/automation/run");
      const data = res.data as {
        archived_total?: number;
        eligible_total?: number;
        status?: string;
      } | null;
      const archived = data?.archived_total ?? 0;
      const eligible = data?.eligible_total ?? 0;
      // "Archived N" was reported even though no archive destination exists
      // and nothing had moved. Say what actually happened.
      if (data?.status === "not_configured") {
        push(
          eligible > 0
            ? `${eligible} record(s) are past their retention threshold, but no archive destination is configured — nothing was moved or deleted.`
            : "Nothing is past its retention threshold yet.",
          "warning",
        );
      } else {
        push(archived > 0 ? `Archived ${archived} record(s)` : "Nothing was old enough to archive");
      }
      await load();
    } catch (e) {
      push(getApiError(e, "Retention run failed"), "error");
    } finally {
      setBusy(false);
    }
  };

  const activeHolds = holds.filter((h) => h.is_active !== false);

  const createHold = async () => {
    const name = holdName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await apiClient.post("/data-lifecycle/legal-holds", {
        name,
        description: holdDescription.trim() || null,
      });
      push(`Legal hold "${name}" created — retention will skip this data`);
      setHoldOpen(false);
      setHoldName("");
      setHoldDescription("");
      await load();
    } catch (e) {
      // Keep the form open so the operator does not retype it.
      push(getApiError(e, "Could not create the legal hold"), "error");
    } finally {
      setBusy(false);
    }
  };

  const releaseHold = async () => {
    const hold = confirmRelease;
    if (!hold) return;
    setConfirmRelease(null);
    setBusy(true);
    try {
      await apiClient.delete(`/data-lifecycle/legal-holds/${hold.id}`);
      push(`Released "${hold.name ?? `Hold #${hold.id}`}" — this data is eligible for retention again`, "warning");
      await load();
    } catch (e) {
      push(getApiError(e, "Could not release the hold"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data retention"
        description="How long each kind of record is kept before it is archived and deleted. Legal holds override archival."
        actions={
          <Button size="sm" onClick={() => setConfirmRun(true)} disabled={busy || loading}>
            <Play size={13} className="mr-1.5" /> Run retention now
          </Button>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : (
        <>
          <Card className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <Archive size={15} className="text-content-tertiary" aria-hidden />
              <h2 className="text-sm font-bold font-display text-content-primary">Policies</h2>
            </div>

            {policies.length === 0 ? (
              <EmptyState
                title="No retention policies"
                description="Without an active policy, data is kept indefinitely. This is what holds the posture score's recover dimension down."
              />
            ) : (
              <div className="space-y-2">
                {policies.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2 last:pb-0"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-content-primary capitalize">
                        {p.data_type.replace(/_/g, " ")}
                      </span>
                      {!p.is_active && (
                        <Badge className="bg-app-subtle text-content-tertiary border-line-subtle">
                          inactive
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-content-secondary font-mono">
                      keep {p.retention_days}d
                      {p.archive_after_days != null && <> · archive {p.archive_after_days}d</>}
                      {p.delete_after_days != null && <> · delete {p.delete_after_days}d</>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                <Gavel size={15} className="text-content-tertiary" aria-hidden />
                <h2 className="text-sm font-bold font-display text-content-primary">
                  Legal holds
                </h2>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setHoldOpen(true)}>
                <Plus size={13} className="mr-1.5" /> New hold
              </Button>
            </div>
            {activeHolds.length === 0 ? (
              <p className="text-xs text-content-tertiary">
                No active holds — retention runs without exception.
              </p>
            ) : (
              <div className="space-y-2">
                {activeHolds.map((h) => (
                  <div key={h.id} className="text-xs border-l-2 border-status-warning/40 pl-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <span className="text-content-primary font-medium">
                          {h.name ?? `Hold #${h.id}`}
                        </span>
                        {h.case_ids && h.case_ids.length > 0 && (
                          <span className="text-content-tertiary">
                            {" "}· {h.case_ids.length} case
                            {h.case_ids.length === 1 ? "" : "s"}
                          </span>
                        )}
                        {h.description && (
                          <p className="text-content-tertiary mt-0.5">{h.description}</p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmRelease(h)}
                        disabled={busy}
                      >
                        Release
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      <Modal open={holdOpen} onClose={() => setHoldOpen(false)} title="New legal hold">
        <div className="space-y-4">
          <p className="text-xs text-content-secondary">
            While a hold is active, retention skips the data it covers — nothing is
            archived or deleted until the hold is released.
          </p>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="hold-name"
            >
              Name
            </label>
            <input
              id="hold-name"
              value={holdName}
              onChange={(e) => setHoldName(e.target.value)}
              placeholder="Acme litigation 2026"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="hold-description"
            >
              Reason
            </label>
            <textarea
              id="hold-description"
              value={holdDescription}
              onChange={(e) => setHoldDescription(e.target.value)}
              rows={3}
              placeholder="Why this data must be preserved"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setHoldOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={createHold} disabled={busy || !holdName.trim()}>
              {busy ? "Saving…" : "Create hold"}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmRelease !== null}
        onCancel={() => setConfirmRelease(null)}
        onConfirm={releaseHold}
        loading={busy}
        tone="danger"
        title="Release this legal hold?"
        message={
          `"${confirmRelease?.name ?? ""}" will stop protecting its data. ` +
          "The next retention run may archive or delete records this hold was preserving."
        }
        confirmLabel="Release hold"
      />

      <ConfirmDialog
        open={confirmRun}
        onCancel={() => setConfirmRun(false)}
        onConfirm={runAutomation}
        loading={busy}
        title="Run retention now?"
        message="Records older than each policy's archive threshold are archived, and anything under an active legal hold is skipped. No archive destination is configured yet, so this run will report what is eligible without moving or deleting anything."
        confirmLabel="Run retention"
      />
    </div>
  );
}
