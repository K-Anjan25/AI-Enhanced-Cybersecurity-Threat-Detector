import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ShieldAlert,
  GitBranch,
  Sparkles,
  Undo2,
  FileText,
  CheckCircle2,
  XCircle,
  RotateCcw,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Button,
  SeverityBadge,
  StatusBadge,
  ConfirmDialog,
  LoadingState,
  EmptyState,
} from "../components/ui";
import AnalystApi from "../api/analystApi";
import type { AnalystCase, BlastNode, Decision } from "../types/analyst";

type DialogKind = "approve" | "decline" | "revert" | null;

const DECISION_BADGE: Record<Decision, { tone: "success" | "warning" | "critical" | "neutral"; label: string }> = {
  pending: { tone: "warning", label: "Awaiting your decision" },
  approved: { tone: "success", label: "Approved" },
  declined: { tone: "neutral", label: "Declined" },
  reverted: { tone: "neutral", label: "Reverted" },
};

const CasePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [data, setData] = useState<AnalystCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [busy, setBusy] = useState(false);
  const [showReport, setShowReport] = useState(false);

  const loadCase = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setData(await AnalystApi.fetchCase(id));
    } catch (err: any) {
      setError(err?.status === 404 ? "That case doesn't exist." : err?.detail || "Failed to load the case");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  const runDecision = async (kind: Exclude<DialogKind, null>) => {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const fn =
        kind === "approve"
          ? AnalystApi.approveCase
          : kind === "decline"
          ? AnalystApi.declineCase
          : AnalystApi.revertCase;
      const updated = await fn(id);
      setData(updated);
      setDialog(null);
    } catch (err: any) {
      setError(err?.detail || `Could not ${kind} this case`);
    } finally {
      setBusy(false);
    }
  };

  const nodeById = useMemo(() => {
    const map = new Map<number, BlastNode>();
    (data?.blast_radius?.nodes ?? []).forEach((n) => map.set(n.id, n));
    return map;
  }, [data]);

  if (loading) return <LoadingState label="Opening the case…" />;

  if (error && !data) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader title="Case" backTo="/feed" crumbs={[{ label: "Decisions", to: "/feed" }, { label: "Case" }]} />
        <Card>
          <EmptyState title="Case unavailable" description={error} />
          <div className="flex justify-center pb-4">
            <Button variant="secondary" onClick={() => navigate("/feed")}>
              Back to decisions
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  const analysis = data.analysis;
  const action = data.proposed_action;
  const badge = DECISION_BADGE[data.decision] ?? DECISION_BADGE.pending;
  const isPending = data.decision === "pending";
  const isApproved = data.decision === "approved";
  const confidencePct = analysis ? Math.round((analysis.confidence ?? 0) * 100) : null;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={analysis?.headline || data.title}
        backTo="/feed"
        crumbs={[{ label: "Decisions", to: "/feed" }, { label: `Case #${data.id}` }]}
        badge={<SeverityBadge severity={data.priority} />}
        actions={<StatusBadge tone={badge.tone} label={badge.label} />}
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical">
          {error}
        </div>
      )}

      {/* Explanation — plain English, calm prose. */}
      <Card>
        <div className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-tertiary mb-1.5">
              What happened
            </h2>
            <p className="text-content-primary leading-relaxed">{analysis?.what_happened || data.description}</p>
          </div>
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-content-tertiary mb-1.5">
              Why it matters
            </h2>
            <p className="text-content-secondary leading-relaxed">{analysis?.why_it_matters}</p>
          </div>
        </div>
      </Card>

      {/* Blast radius */}
      <Card padded={false} className="overflow-hidden">
        <div className="px-5 py-4 border-b border-line-subtle flex items-center gap-2">
          <GitBranch size={16} className="text-accent-primary" aria-hidden />
          <h2 className="text-sm font-semibold text-content-primary font-display tracking-tight">Blast radius</h2>
          <span className="text-xs text-content-tertiary ml-auto">
            {data.blast_radius?.nodes?.length ?? 0} assets touched
          </span>
        </div>
        {analysis?.blast_radius_summary && (
          <p className="px-5 pt-4 text-sm text-content-secondary leading-relaxed">{analysis.blast_radius_summary}</p>
        )}
        <ul className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {(data.blast_radius?.nodes ?? []).map((n) => {
            const isRoot = n.id === data.blast_radius?.root_entity_id;
            return (
              <li
                key={n.id}
                className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-line-subtle bg-app-subtle/40"
              >
                <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-app-subtle text-content-tertiary border border-line-subtle shrink-0">
                  {n.entity_type}
                </span>
                <span className="text-sm text-content-primary font-mono truncate" title={n.value}>
                  {n.value}
                </span>
                {isRoot && (
                  <span className="ml-auto text-[10px] font-semibold uppercase tracking-wider text-accent-primary shrink-0">
                    origin
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        {(data.blast_radius?.links?.length ?? 0) > 0 && (
          <div className="px-5 pb-5 space-y-1.5">
            {data.blast_radius!.links.map((l, i) => (
              <p key={i} className="text-xs text-content-tertiary font-mono">
                {nodeById.get(l.source)?.value ?? l.source}
                <span className="text-accent-primary"> —{l.relation}→ </span>
                {nodeById.get(l.target)?.value ?? l.target}
              </p>
            ))}
          </div>
        )}
      </Card>

      {/* Recommended action */}
      {action && (
        <Card className="border-accent-primary/30">
          <div className="flex items-start gap-3">
            <span className="w-10 h-10 rounded-lg bg-accent-primary/15 text-accent-primary flex items-center justify-center shrink-0">
              <ShieldAlert size={20} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-content-tertiary">
                  Recommended action
                </h2>
                <p className="mt-1 text-lg font-semibold text-content-primary font-display">
                  <span className="font-mono">{action.action_type}</span>
                </p>
                <p className="text-sm text-content-secondary mt-0.5">
                  Target: <span className="font-mono text-content-primary">{action.target}</span>
                </p>
              </div>
              {action.rationale && (
                <p className="text-sm text-content-secondary leading-relaxed">{action.rationale}</p>
              )}
              {action.undo && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-status-success/10 border border-status-success/30">
                  <Undo2 size={15} className="text-status-success mt-0.5 shrink-0" aria-hidden />
                  <p className="text-xs text-content-secondary">
                    <span className="font-semibold text-status-success">Reversible.</span> {action.undo}
                  </p>
                </div>
              )}
              <div className="flex items-center gap-3 text-xs text-content-tertiary pt-1">
                <span className="inline-flex items-center gap-1">
                  <Sparkles size={12} aria-hidden />
                  {analysis?.fallback
                    ? "NOCTRA built-in reasoning (no LLM key configured)"
                    : `Reasoned by ${analysis?.model ?? "Claude"}`}
                </span>
                {confidencePct !== null && <span>· {confidencePct}% confidence</span>}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Decision gate */}
      <Card>
        {isPending ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-content-primary">This one's your call.</p>
              <p className="text-xs text-content-tertiary mt-0.5">
                Approving records the action and generates a report. You can reverse it afterwards.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button variant="secondary" onClick={() => setDialog("decline")}>
                Decline
              </Button>
              <Button variant="primary" onClick={() => setDialog("approve")}>
                <CheckCircle2 size={16} className="mr-1.5" aria-hidden />
                Approve action
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <span
                className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                  isApproved ? "bg-status-success/15 text-status-success" : "bg-app-subtle text-content-secondary"
                }`}
              >
                {isApproved ? <CheckCircle2 size={18} aria-hidden /> : data.decision === "reverted" ? <RotateCcw size={18} aria-hidden /> : <XCircle size={18} aria-hidden />}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-content-primary capitalize">{data.decision}</p>
                <p className="text-xs text-content-tertiary mt-0.5">
                  {data.decided_at ? new Date(data.decided_at).toLocaleString() : "Recorded"}
                  {data.soar_action_id && (
                    <>
                      {" · action "}
                      <span className="font-mono">{data.soar_action_id}</span>
                    </>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-2 ml-auto shrink-0">
                {data.report && (
                  <Button variant="ghost" onClick={() => setShowReport((s) => !s)}>
                    <FileText size={16} className="mr-1.5" aria-hidden />
                    {showReport ? "Hide report" : "View report"}
                  </Button>
                )}
                {isApproved && (
                  <Button variant="secondary" onClick={() => setDialog("revert")}>
                    <Undo2 size={16} className="mr-1.5" aria-hidden />
                    Reverse
                  </Button>
                )}
              </div>
            </div>

            {showReport && data.report && (
              <pre className="p-4 rounded-lg bg-app-subtle/60 border border-line-subtle text-xs text-content-secondary whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
                {data.report}
              </pre>
            )}
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={dialog === "approve"}
        tone="primary"
        title="Approve this action?"
        message={
          <>
            NOCTRA will record <span className="font-mono">{action?.action_type}</span> on{" "}
            <span className="font-mono">{action?.target}</span> and generate a report. This is reversible.
          </>
        }
        confirmLabel="Approve"
        loading={busy}
        onConfirm={() => runDecision("approve")}
        onCancel={() => setDialog(null)}
      />
      <ConfirmDialog
        open={dialog === "decline"}
        tone="danger"
        title="Decline this recommendation?"
        message="The case is closed with no action taken. It stays on record in your feed."
        confirmLabel="Decline"
        loading={busy}
        onConfirm={() => runDecision("decline")}
        onCancel={() => setDialog(null)}
      />
      <ConfirmDialog
        open={dialog === "revert"}
        tone="danger"
        title="Reverse this action?"
        message={
          <>
            NOCTRA records a compensating action{action?.undo ? <> — {action.undo}</> : null} and marks the case reverted.
          </>
        }
        confirmLabel="Reverse"
        loading={busy}
        onConfirm={() => runDecision("revert")}
        onCancel={() => setDialog(null)}
      />
    </div>
  );
};

export default CasePage;
