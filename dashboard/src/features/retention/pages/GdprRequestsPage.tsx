import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, ShieldQuestion, TriangleAlert } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Modal,
  PageHeader,
  SkeletonCard,
  StatCard,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";

/**
 * Right-to-erasure requests.
 *
 * A GDPR erasure request carries a statutory clock — a controller has one month
 * to respond. The backend has always accepted, listed and processed these, but
 * nothing in the dashboard could action them, so the queue was invisible and a
 * request could sit unanswered indefinitely. That is a compliance gap rather
 * than a missing feature, which is why this page exists.
 *
 * Approving is irreversible: the subject's account is anonymised in place. The
 * page says so before asking, and the backend refuses to re-decide a request
 * that has already been settled.
 */

interface GdprRequest {
  id: number;
  target_email: string | null;
  reason: string | null;
  status: string;
  created_at: string | null;
  completed_at: string | null;
}

const asList = (v: unknown): GdprRequest[] => (Array.isArray(v) ? (v as GdprRequest[]) : []);

const STATUS_TONE: Record<string, string> = {
  pending: "bg-status-warning/10 text-status-warning border-status-warning/30",
  approved: "bg-accent-primary/10 text-accent-primary border-accent-primary/30",
  completed: "bg-status-success/10 text-status-success border-status-success/30",
  rejected: "bg-app-subtle text-content-tertiary border-line-subtle",
};

/** Days since a request arrived — the number that matters for the deadline. */
const ageInDays = (iso: string | null): number | null => {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / 86_400_000);
};

type PendingAction = { request: GdprRequest; action: "approve" | "reject" };

export default function GdprRequestsPage() {
  const [requests, setRequests] = useState<GdprRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [confirm, setConfirm] = useState<PendingAction | null>(null);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const { push } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/data-lifecycle/gdpr");
      setRequests(asList(res.data));
      setFailed(false);
    } catch (e) {
      // An unreachable queue is not an empty queue.
      setFailed(true);
      push(getApiError(e, "Could not load erasure requests"), "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = useMemo(
    () => requests.filter((r) => r.status === "pending"),
    [requests],
  );
  const overdue = useMemo(
    () => pending.filter((r) => (ageInDays(r.created_at) ?? 0) > 30),
    [pending],
  );

  const submit = async () => {
    const target = email.trim();
    if (!target) return;
    setBusy(true);
    try {
      await apiClient.post("/data-lifecycle/gdpr", {
        target_email: target,
        reason: reason.trim() || null,
      });
      push(`Erasure request logged for ${target}`);
      setOpen(false);
      setEmail("");
      setReason("");
      await load();
    } catch (e) {
      push(getApiError(e, "Could not log the request"), "error");
    } finally {
      setBusy(false);
    }
  };

  const decide = async () => {
    if (!confirm) return;
    const { request, action } = confirm;
    setConfirm(null);
    setBusy(true);
    try {
      await apiClient.post(`/data-lifecycle/gdpr/${request.id}/${action}`);
      push(
        action === "approve"
          ? `Erasure approved — ${request.target_email ?? "the account"} has been anonymised`
          : `Request rejected for ${request.target_email ?? "this subject"}`,
        action === "approve" ? "warning" : "success",
      );
      await load();
    } catch (e) {
      push(getApiError(e, "Could not process the request"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Erasure requests"
        description="Right-to-erasure requests under GDPR. Approving anonymises the subject's account and cannot be undone."
        actions={
          <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
            <Plus size={13} className="mr-1.5" /> Log request
          </Button>
        }
      />

      {loading ? (
        <SkeletonCard />
      ) : failed ? (
        <EmptyState
          title="Erasure queue unavailable"
          description="The requests could not be loaded. This is a failure, not an empty queue — a pending request may still be waiting."
          action={
            <Button size="sm" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Awaiting decision" value={pending.length} />
            <StatCard
              label="Past 30 days"
              value={overdue.length}
              tone={overdue.length > 0 ? "critical" : "default"}
            />
            <StatCard label="Total logged" value={requests.length} />
          </div>

          {overdue.length > 0 && (
            <Card className="p-4 border-status-critical/40">
              <div className="flex items-start gap-2">
                <TriangleAlert
                  size={15}
                  className="text-status-critical shrink-0 mt-0.5"
                  aria-hidden
                />
                <p className="text-xs text-content-secondary">
                  <span className="font-medium text-content-primary">
                    {overdue.length} request{overdue.length === 1 ? " has" : "s have"} been
                    open longer than 30 days.
                  </span>{" "}
                  A controller is normally required to respond within one month of
                  receiving an erasure request.
                </p>
              </div>
            </Card>
          )}

          {requests.length === 0 ? (
            <EmptyState
              icon={<ShieldQuestion size={20} />}
              title="No erasure requests"
              description="Nothing has been logged yet. Requests appear here when a data subject asks for their personal data to be deleted."
            />
          ) : (
            <Card className="p-5">
              <div className="space-y-2">
                {requests.map((r) => {
                  const age = ageInDays(r.created_at);
                  const isPending = r.status === "pending";
                  return (
                    <div
                      key={r.id}
                      className="flex items-start justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-2.5 last:pb-0"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-content-primary">
                            {r.target_email ?? `Subject #${r.id}`}
                          </span>
                          <Badge
                            className={STATUS_TONE[r.status] ?? STATUS_TONE.rejected}
                          >
                            {r.status}
                          </Badge>
                          {isPending && age !== null && (
                            <span
                              className={
                                age > 30
                                  ? "text-[11px] text-status-critical"
                                  : "text-[11px] text-content-tertiary"
                              }
                            >
                              open {age} day{age === 1 ? "" : "s"}
                            </span>
                          )}
                        </div>
                        {r.reason && (
                          <p className="text-xs text-content-tertiary mt-0.5">{r.reason}</p>
                        )}
                      </div>

                      {isPending ? (
                        <div className="flex items-center gap-2 shrink-0">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => setConfirm({ request: r, action: "reject" })}
                          >
                            Reject
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            disabled={busy}
                            onClick={() => setConfirm({ request: r, action: "approve" })}
                          >
                            Approve erasure
                          </Button>
                        </div>
                      ) : (
                        <span className="text-[11px] text-content-tertiary shrink-0">
                          {r.status === "rejected" ? "No action taken" : "Settled"}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="Log an erasure request">
        <div className="space-y-4">
          <p className="text-xs text-content-secondary">
            Record a request received from a data subject. Logging it starts the clock;
            nothing is deleted until someone approves it here.
          </p>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="gdpr-email"
            >
              Subject email
            </label>
            <input
              id="gdpr-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@example.com"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="gdpr-reason"
            >
              Reason
            </label>
            <textarea
              id="gdpr-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="How the request was received, and any reference"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} disabled={busy || !email.trim()}>
              {busy ? "Saving…" : "Log request"}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirm !== null}
        onCancel={() => setConfirm(null)}
        onConfirm={decide}
        loading={busy}
        tone={confirm?.action === "approve" ? "danger" : "primary"}
        title={
          confirm?.action === "approve"
            ? "Approve this erasure?"
            : "Reject this request?"
        }
        message={
          confirm?.action === "approve"
            ? `The account for ${confirm?.request.target_email ?? "this subject"} will be anonymised in place: the email and username are overwritten and the account is deactivated. This cannot be undone, and the request cannot be re-decided afterwards.`
            : `The request from ${confirm?.request.target_email ?? "this subject"} will be marked rejected and no data will be deleted. Make sure the refusal is lawful and that the subject is told why.`
        }
        confirmLabel={confirm?.action === "approve" ? "Anonymise account" : "Reject request"}
      />
    </div>
  );
}
