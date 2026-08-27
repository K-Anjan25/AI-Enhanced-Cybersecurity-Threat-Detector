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
  MessageSquare,
  Send,
  Bot,
  User,
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
import type { AnalystCase, BlastNode, Decision, ChatMessage } from "../types/analyst";

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

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const loadCase = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const c = await AnalystApi.fetchCase(id);
      setData(c);
      // Seed initial welcome message from AXIOM AI
      setChatMessages([
        {
          id: "welcome",
          sender: "axiom",
          text: `Hello! I am AXIOM AI analyst. Ask me anything about Case #${c.id} (${c.title}).`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } catch (err: any) {
      setError(err?.status === 404 ? "That case doesn't exist." : err?.detail || "Failed to load the case");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !id || chatLoading) return;

    const userText = chatInput.trim();
    setChatInput("");
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setChatLoading(true);

    try {
      const res = await AnalystApi.chatAboutCase(id, userText);
      const axiomMsg: ChatMessage = {
        id: `n-${Date.now()}`,
        sender: "axiom",
        text: res.answer,
        confidence: res.confidence,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setChatMessages((prev) => [...prev, axiomMsg]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          sender: "axiom",
          text: "I couldn't process that question right now. Please try again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

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
      <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
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
    <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
      <PageHeader
        title={analysis?.headline || data.title}
        backTo="/feed"
        crumbs={[{ label: "Decisions", to: "/feed" }, { label: `Case #${data.id}` }]}
        badge={<SeverityBadge severity={data.priority} />}
        actions={<StatusBadge tone={badge.tone} label={badge.label} />}
      />

      {error && (
        <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600 font-medium">
          {error}
        </div>
      )}

      {/* Explanation — plain English, calm prose. */}
      <div className="bg-white rounded-2xl border border-line-subtle p-6 shadow-card space-y-4">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
            What happened
          </h2>
          <p className="text-slate-800 leading-relaxed font-medium">{analysis?.what_happened || data.description}</p>
        </div>
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
            Why it matters
          </h2>
          <p className="text-slate-600 leading-relaxed">{analysis?.why_it_matters}</p>
        </div>
      </div>

      {/* Blast radius */}
      <div className="bg-[#0e1320] text-white rounded-2xl border border-slate-800 overflow-hidden shadow-navy">
        <div className="px-5 py-4 border-b border-slate-800 flex items-center gap-2">
          <GitBranch size={16} className="text-blue-400" aria-hidden />
          <h2 className="text-sm font-bold text-white font-display tracking-tight">Blast Radius Affected Assets</h2>
          <span className="text-xs text-slate-400 ml-auto font-mono">
            {data.blast_radius?.nodes?.length ?? 0} assets touched
          </span>
        </div>
        {analysis?.blast_radius_summary && (
          <p className="px-5 pt-4 text-sm text-slate-300 leading-relaxed">{analysis.blast_radius_summary}</p>
        )}
        <ul className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {(data.blast_radius?.nodes ?? []).map((n) => {
            const isRoot = n.id === data.blast_radius?.root_entity_id;
            return (
              <li
                key={n.id}
                className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl border border-slate-700 bg-slate-900/80"
              >
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 shrink-0">
                  {n.entity_type}
                </span>
                <span className="text-xs text-slate-200 font-mono truncate" title={n.value}>
                  {n.value}
                </span>
                {isRoot && (
                  <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-blue-400 shrink-0">
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
              <p key={i} className="text-xs text-slate-400 font-mono">
                {nodeById.get(l.source)?.value ?? l.source}
                <span className="text-blue-400"> —{l.relation}→ </span>
                {nodeById.get(l.target)?.value ?? l.target}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Recommended action */}
      {action && (
        <div className="bg-white rounded-2xl border border-blue-200 p-6 shadow-card">
          <div className="flex items-start gap-3">
            <span className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
              <ShieldAlert size={20} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Recommended Action
                </h2>
                <p className="mt-1 text-lg font-bold text-slate-900 font-display">
                  <span className="font-mono text-blue-600">{action.action_type}</span>
                </p>
                <p className="text-sm text-slate-600 mt-0.5">
                  Target: <span className="font-mono text-slate-900 font-bold">{action.target}</span>
                </p>
              </div>
              {action.rationale && (
                <p className="text-sm text-slate-600 leading-relaxed">{action.rationale}</p>
              )}
              {action.undo && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-emerald-50 border border-emerald-200">
                  <Undo2 size={15} className="text-emerald-600 mt-0.5 shrink-0" aria-hidden />
                  <p className="text-xs text-slate-700">
                    <span className="font-bold text-emerald-700">Reversible.</span> {action.undo}
                  </p>
                </div>
              )}
              <div className="flex items-center gap-3 text-xs text-slate-500 pt-1">
                <span className="inline-flex items-center gap-1 font-medium">
                  <Sparkles size={12} className="text-blue-600" aria-hidden />
                  {analysis?.fallback
                    ? "AXIOM AI built-in reasoning engine"
                    : `Reasoned by ${analysis?.model ?? "Claude"}`}
                </span>
                {confidencePct !== null && <span>· {confidencePct}% confidence</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Ask-AXIOM AI Interactive Analyst Chat */}
      <div className="bg-[#0e1320] text-white rounded-2xl border border-slate-800 overflow-hidden shadow-navy">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center gap-2 bg-slate-900/60">
          <MessageSquare size={16} className="text-blue-400" />
          <h2 className="text-sm font-bold text-white font-display tracking-tight">
            Ask AXIOM AI Analyst
          </h2>
          <span className="text-xs text-slate-400 ml-auto font-mono">
            Interactive Q&A
          </span>
        </div>

        <div className="p-5 max-h-72 overflow-y-auto space-y-3.5">
          {chatMessages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-2.5 ${
                msg.sender === "user" ? "flex-row-reverse" : ""
              }`}
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs shrink-0 ${
                  msg.sender === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-800 text-blue-400 border border-slate-700"
                }`}
              >
                {msg.sender === "user" ? <User size={14} /> : <Bot size={14} />}
              </div>
              <div
                className={`max-w-[80%] p-3 rounded-xl text-xs leading-relaxed ${
                  msg.sender === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-900 border border-slate-800 text-slate-200"
                }`}
              >
                <p>{msg.text}</p>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>{msg.timestamp}</span>
                  {msg.confidence !== undefined && (
                    <span>Confidence: {Math.round(msg.confidence * 100)}%</span>
                  )}
                </div>
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-400 animate-pulse">
              <Bot size={14} className="text-blue-400" /> AXIOM AI is reasoning…
            </div>
          )}
        </div>

        <form onSubmit={handleSendMessage} className="p-3 border-t border-slate-800 flex gap-2 bg-slate-950">
          <input
            type="text"
            placeholder="Ask about blast radius, threat actor, or remediation details..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            disabled={chatLoading}
            className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          <Button type="submit" variant="primary" size="sm" disabled={chatLoading || !chatInput.trim()} className="bg-blue-600 hover:bg-blue-700 text-white">
            <Send size={14} />
          </Button>
        </form>
      </div>

      {/* Decision gate */}
      <div className="bg-white rounded-2xl border border-line-subtle p-6 shadow-card">
        {isPending ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-slate-900">This one's your call.</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Approving records the action and generates a report. You can reverse it afterwards.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button variant="secondary" onClick={() => setDialog("decline")}>
                Decline
              </Button>
              <Button variant="primary" onClick={() => setDialog("approve")} className="bg-blue-600 hover:bg-blue-700 text-white font-bold">
                <CheckCircle2 size={16} className="mr-1.5" aria-hidden />
                Approve Action
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <span
                className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                  isApproved ? "bg-emerald-100 text-emerald-600" : "bg-slate-100 text-slate-600"
                }`}
              >
                {isApproved ? <CheckCircle2 size={18} aria-hidden /> : data.decision === "reverted" ? <RotateCcw size={18} aria-hidden /> : <XCircle size={18} aria-hidden />}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold text-slate-900 capitalize">{data.decision}</p>
                <p className="text-xs text-slate-500 mt-0.5">
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
              <pre className="p-4 rounded-xl bg-slate-900 text-slate-200 border border-slate-800 text-xs whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
                {data.report}
              </pre>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={dialog === "approve"}
        tone="primary"
        title="Approve this action?"
        message={
          <>
            AXIOM AI will record <span className="font-mono font-bold">{action?.action_type}</span> on{" "}
            <span className="font-mono font-bold">{action?.target}</span> and generate a report. This is reversible.
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
        message="The case is closed with no action taken. It stays on record in your decision feed."
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
            AXIOM AI records a compensating action{action?.undo ? <> — {action.undo}</> : null} and marks the case reverted.
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
