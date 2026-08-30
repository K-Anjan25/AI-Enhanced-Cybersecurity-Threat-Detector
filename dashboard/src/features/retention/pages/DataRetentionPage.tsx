import React, { useCallback, useEffect, useState } from "react";
import { Archive, Gavel, Play } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
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

interface LegalHold {
  id: number;
  name?: string | null;
  reason?: string | null;
  data_type?: string | null;
  is_active?: boolean;
}

const asList = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

export default function DataRetentionPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [holds, setHolds] = useState<LegalHold[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
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
      const results = asList<{ archived?: number }>(res.data?.results ?? res.data);
      const total = results.reduce((n, r) => n + (r?.archived ?? 0), 0);
      push(total > 0 ? `Archived ${total} record(s)` : "Nothing was old enough to archive");
      await load();
    } catch (e) {
      push(getApiError(e, "Retention run failed"), "error");
    } finally {
      setBusy(false);
    }
  };

  const activeHolds = holds.filter((h) => h.is_active !== false);

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
            <div className="flex items-center gap-2 mb-3">
              <Gavel size={15} className="text-content-tertiary" aria-hidden />
              <h2 className="text-sm font-bold font-display text-content-primary">Legal holds</h2>
            </div>
            {activeHolds.length === 0 ? (
              <p className="text-xs text-content-tertiary">
                No active holds — retention runs without exception.
              </p>
            ) : (
              <div className="space-y-2">
                {activeHolds.map((h) => (
                  <div key={h.id} className="text-xs border-l-2 border-status-warning/40 pl-3">
                    <span className="text-content-primary font-medium">{h.name ?? `Hold #${h.id}`}</span>
                    {h.data_type && (
                      <span className="text-content-tertiary"> · {h.data_type}</span>
                    )}
                    {h.reason && <p className="text-content-tertiary mt-0.5">{h.reason}</p>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      <ConfirmDialog
        open={confirmRun}
        onCancel={() => setConfirmRun(false)}
        onConfirm={runAutomation}
        loading={busy}
        title="Run retention now?"
        message="Records older than each policy's archive threshold will be archived. Anything under an active legal hold is skipped. This cannot be undone from the UI."
        confirmLabel="Run retention"
      />
    </div>
  );
}
