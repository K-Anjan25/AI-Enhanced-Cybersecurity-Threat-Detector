import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import apiClient from "../../../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  SkeletonCard,
  StatCard,
} from "../../../components/ui";
import { useToast } from "../../../components/ui/Toast";
import { getApiError } from "../../../utils/getApiError";
import { useSelector } from "react-redux";
import type { RootState } from "../../../store/store";

/**
 * Approval queue — the second pair of eyes before a destructive action runs.
 *
 * The backend has always supported multi-stage approvals, but nothing surfaced
 * them, so a queued request was invisible: the action waited and no one knew.
 * That is the whole point of a human-on-the-loop model, so this page is the
 * queue itself rather than a settings screen.
 *
 * Separation of duties is enforced server-side. This page mirrors it — the
 * buttons are hidden on your own requests — but the rule that matters is the
 * one the API refuses, not the one the UI hides.
 */

interface ApprovalRecord {
  user_id: number;
  decision: string;
  comment: string | null;
  step: number;
  at: string;
}

interface Instance {
  id: number;
  workflow_id: number;
  workflow_name: string | null;
  action_type: string;
  target: string | null;
  case_id: number | null;
  current_step: number;
  total_steps: number | null;
  status: string;
  requested_by_user_id: number | null;
  approvals: ApprovalRecord[] | null;
  created_at: string | null;
  decided_at: string | null;
}

const asList = (v: unknown): Instance[] => (Array.isArray(v) ? (v as Instance[]) : []);

const STATUS_TONE: Record<string, string> = {
  pending: "bg-status-warning/10 text-status-warning border-status-warning/30",
  approved: "bg-status-success/10 text-status-success border-status-success/30",
  rejected: "bg-app-subtle text-content-tertiary border-line-subtle",
};

/** "isolate_host" reads badly in a queue an operator scans quickly. */
const humanAction = (raw: string): string =>
  raw.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const waitingFor = (iso: string | null): string => {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(mins) || mins < 1) return "just now";
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
};

type Decision = { instance: Instance; decision: "approved" | "rejected" };

export default function ApprovalsPage() {
  const [instances, setInstances] = useState<Instance[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<Decision | null>(null);
  const [comment, setComment] = useState("");
  const { push } = useToast();
  // userId is stored as a string; instances carry a numeric id.
  const currentUserId = useSelector((state: RootState) => {
    const raw = state.user.user?.userId ?? state.user.user?.id;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && raw !== "" && raw != null ? parsed : null;
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/approval-workflows/instances");
      setInstances(asList(res.data));
      setFailed(false);
    } catch (e) {
      // A queue that failed to load is not an empty queue: an action may be
      // waiting on an approval nobody can see.
      setFailed(true);
      push(getApiError(e, "Could not load the approval queue"), "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = useMemo(
    () => instances.filter((i) => i.status === "pending"),
    [instances],
  );
  const mine = useMemo(
    () => pending.filter((i) => i.requested_by_user_id === currentUserId),
    [pending, currentUserId],
  );

  const submit = async () => {
    if (!pendingDecision) return;
    const { instance, decision } = pendingDecision;
    setBusy(true);
    try {
      await apiClient.post(`/approval-workflows/instances/${instance.id}/decide`, {
        decision,
        comment: comment.trim() || null,
      });
      push(
        decision === "approved"
          ? `Approved — ${humanAction(instance.action_type)} on ${instance.target ?? "the target"} can proceed`
          : `Rejected — ${humanAction(instance.action_type)} will not run`,
        decision === "approved" ? "success" : "warning",
      );
      setPendingDecision(null);
      setComment("");
      await load();
    } catch (e) {
      // Includes the server refusing on separation-of-duties grounds.
      push(getApiError(e, "Could not record the decision"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        description="Actions waiting on a human decision before they run. You cannot approve a request you raised yourself."
      />

      {loading ? (
        <SkeletonCard />
      ) : failed ? (
        <EmptyState
          title="Approval queue unavailable"
          description="The queue could not be loaded. This is a failure, not an empty queue — an action may be waiting on an approval."
          action={
            <Button size="sm" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Waiting on a decision" value={pending.length} />
            <StatCard label="Raised by you" value={mine.length} />
            <StatCard label="Total in queue" value={instances.length} />
          </div>

          {mine.length > 0 && (
            <Card className="p-4">
              <div className="flex items-start gap-2">
                <TriangleAlert
                  size={15}
                  className="text-status-warning shrink-0 mt-0.5"
                  aria-hidden
                />
                <p className="text-xs text-content-secondary">
                  {mine.length} of these {mine.length === 1 ? "was" : "were"} raised by
                  you and {mine.length === 1 ? "needs" : "need"} someone else to decide.
                </p>
              </div>
            </Card>
          )}

          {instances.length === 0 ? (
            <EmptyState
              icon={<ShieldCheck size={20} />}
              title="Nothing waiting for approval"
              description="Actions that need a second pair of eyes appear here. An empty queue means nothing is blocked."
            />
          ) : (
            <Card className="p-5">
              <div className="space-y-3">
                {instances.map((i) => {
                  const isMine = i.requested_by_user_id === currentUserId;
                  const isPending = i.status === "pending";
                  const decided = i.approvals ?? [];
                  return (
                    <div
                      key={i.id}
                      className="flex items-start justify-between gap-3 flex-wrap border-b border-line-subtle last:border-0 pb-3 last:pb-0"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-content-primary">
                            {humanAction(i.action_type)}
                          </span>
                          {i.target && (
                            <span className="text-xs font-mono text-content-secondary">
                              {i.target}
                            </span>
                          )}
                          <Badge className={STATUS_TONE[i.status] ?? STATUS_TONE.rejected}>
                            {i.status}
                          </Badge>
                          {isPending && i.total_steps && i.total_steps > 1 && (
                            <span className="text-[11px] text-content-tertiary">
                              stage {i.current_step} of {i.total_steps}
                            </span>
                          )}
                          {isPending && (
                            <span className="text-[11px] text-content-tertiary">
                              waiting {waitingFor(i.created_at)}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-content-tertiary mt-0.5">
                          {i.workflow_name ?? `Workflow #${i.workflow_id}`}
                          {i.case_id ? ` · case #${i.case_id}` : ""}
                          {isMine ? " · raised by you" : ""}
                        </p>
                        {decided.length > 0 && (
                          <p className="text-[11px] text-content-tertiary mt-1">
                            {decided.length} decision{decided.length === 1 ? "" : "s"}{" "}
                            recorded so far
                          </p>
                        )}
                      </div>

                      {isPending &&
                        (isMine ? (
                          <span className="text-[11px] text-content-tertiary shrink-0 max-w-[13rem] text-right">
                            You raised this, so someone else has to decide it.
                          </span>
                        ) : (
                          <div className="flex items-center gap-2 shrink-0">
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() =>
                                setPendingDecision({ instance: i, decision: "rejected" })
                              }
                            >
                              <XCircle size={13} className="mr-1.5" /> Reject
                            </Button>
                            <Button
                              size="sm"
                              disabled={busy}
                              onClick={() =>
                                setPendingDecision({ instance: i, decision: "approved" })
                              }
                            >
                              <CheckCircle2 size={13} className="mr-1.5" /> Approve
                            </Button>
                          </div>
                        ))}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </>
      )}

      <Modal
        open={pendingDecision !== null}
        onClose={() => setPendingDecision(null)}
        title={
          pendingDecision?.decision === "approved"
            ? "Approve this action?"
            : "Reject this action?"
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-content-secondary">
            {pendingDecision?.decision === "approved" ? (
              <>
                <span className="font-medium text-content-primary">
                  {humanAction(pendingDecision?.instance.action_type ?? "")}
                </span>{" "}
                will run against{" "}
                <span className="font-mono">
                  {pendingDecision?.instance.target ?? "the target"}
                </span>
                {pendingDecision?.instance.total_steps &&
                pendingDecision.instance.total_steps > 1 &&
                pendingDecision.instance.current_step < pendingDecision.instance.total_steps
                  ? " once the remaining stage is approved."
                  : " as soon as this is recorded."}
              </>
            ) : (
              <>
                The action will not run. The person who raised it should be told why, so
                a comment is worth leaving.
              </>
            )}
          </p>
          <div>
            <label
              className="tech-label text-content-tertiary block mb-1.5"
              htmlFor="approval-comment"
            >
              Comment
            </label>
            <textarea
              id="approval-comment"
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Recorded against your name in the audit trail"
              className="w-full bg-app-subtle border border-line-subtle rounded-sm px-3 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPendingDecision(null)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              variant={pendingDecision?.decision === "approved" ? "primary" : "danger"}
              onClick={submit}
              disabled={busy}
            >
              {busy
                ? "Recording…"
                : pendingDecision?.decision === "approved"
                  ? "Approve"
                  : "Reject"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
