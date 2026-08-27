import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
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
  ArrowLeft,
  Lock,
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
  pending: { tone: "warning", label: "Awaiting decision" },
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
      // Seed initial welcome message from NOCTRA
      setChatMessages([
        {
          id: "welcome",
          sender: "noctra",
          text: `Hello! I am NOCTRA AI analyst. Ask me anything about Case #${c.id} (${c.title}).`,
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
      const noctraMsg: ChatMessage = {
        id: `n-${Date.now()}`,
        sender: "noctra",
        text: res.answer,
        confidence: res.confidence,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setChatMessages((prev) => [...prev, noctraMsg]);
    } catch (err: any) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          sender: "noctra",
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

  if (loading) return <LoadingState label="NOCTRA is preparing the case workspace…" />;

  if (error && !data) {
    return (
      <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
        <PageHeader title="Case" backTo="/feed" crumbs={[{ label: "Cases", to: "/feed" }, { label: "Case" }]} />
        <Card className="bg-card-bg border-card-border">
          <EmptyState title="Case unavailable" description={error} />
          <div className="flex justify-center pb-4">
            <Button variant="secondary" onClick={() => navigate("/feed")}>
              Back to Cases
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
      {/* Case Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-card-bg p-6 rounded-2xl border border-card-border shadow-card">
        <div>
          <Link to="/feed" className="inline-flex items-center text-xs font-bold text-slate-400 hover:text-accent-amber mb-2">
            <ArrowLeft size={14} className="mr-1" /> Back to Cases
          </Link>
          <h1 className="text-xl font-bold font-display text-content-primary">
            Case #{data.id}: {analysis?.headline || data.title}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <SeverityBadge severity={data.priority} />
          <StatusBadge tone={badge.tone} label={badge.label} />
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-400 font-medium">
          {error}
        </div>
      )}

      {/* 2-Column Split Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column (65%): Analysis, Blast Radius & Evidence */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* Executive Summary Narrative */}
          <div className="bg-card-bg rounded-2xl border border-card-border p-6 shadow-card space-y-4">
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                What Happened
              </h2>
              <p className="text-sm text-content-primary leading-relaxed font-medium">
                {analysis?.what_happened || data.description}
              </p>
            </div>
            <div className="border-t border-card-border pt-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                Why It Matters
              </h2>
              <p className="text-xs text-content-secondary leading-relaxed">
                {analysis?.why_it_matters || "Unaddressed credential misuse permits unauthorized access to internal records."}
              </p>
            </div>
          </div>

          {/* Blast Radius Mapping */}
          <div className="bg-card-bg rounded-2xl border border-card-border overflow-hidden shadow-card">
            <div className="px-6 py-4 border-b border-card-border flex items-center gap-2 bg-app-void">
              <GitBranch size={16} className="text-accent-amber" />
              <h2 className="text-sm font-bold text-content-primary font-display">
                Blast Radius & Connected Assets
              </h2>
              <span className="text-xs text-slate-400 ml-auto font-mono">
                {data.blast_radius?.nodes?.length ?? 0} assets touched
              </span>
            </div>

            {analysis?.blast_radius_summary && (
              <p className="px-6 pt-4 text-xs text-slate-300 leading-relaxed">
                {analysis.blast_radius_summary}
              </p>
            )}

            <ul className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(data.blast_radius?.nodes ?? []).map((n) => {
                const isRoot = n.id === data.blast_radius?.root_entity_id;
                return (
                  <li
                    key={n.id}
                    className="flex items-center gap-2.5 px-3.5 py-3 rounded-xl border border-card-border bg-app-void"
                  >
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-card-bg text-slate-300 border border-card-border shrink-0">
                      {n.entity_type}
                    </span>
                    <span className="text-xs text-slate-200 font-mono truncate" title={n.value}>
                      {n.value}
                    </span>
                    {isRoot && (
                      <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-accent-amber shrink-0">
                        origin
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>

            {(data.blast_radius?.links?.length ?? 0) > 0 && (
              <div className="px-6 pb-6 space-y-1.5 border-t border-card-border pt-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                  Asset Relationship Paths
                </p>
                {data.blast_radius!.links.map((l, i) => (
                  <p key={i} className="text-xs text-slate-400 font-mono">
                    {nodeById.get(l.source)?.value ?? l.source}
                    <span className="text-accent-amber"> —{l.relation}→ </span>
                    {nodeById.get(l.target)?.value ?? l.target}
                  </p>
                ))}
              </div>
            )}
          </div>

          {/* Technical Evidence Accordion */}
          <div className="bg-card-bg rounded-2xl border border-card-border p-6 shadow-card space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Technical Evidence & MITRE Mapping
            </h2>
            <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
              <span className="px-3 py-1.5 rounded-xl bg-app-void border border-card-border text-slate-300">
                MITRE Technique: <span className="text-accent-amber font-bold">T1078 (Valid Accounts)</span>
              </span>
              <span className="px-3 py-1.5 rounded-xl bg-app-void border border-card-border text-slate-300">
                Source Alert ID: <span className="text-slate-200">{data.source_alert_id || "evt_99420"}</span>
              </span>
            </div>
          </div>

        </div>

        {/* Right Column (35%): Action, Decision Gate & Copilot Chat */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Recommended Action Card */}
          {action && (
            <div className="bg-card-bg rounded-2xl border border-accent-amber/30 p-6 shadow-card space-y-4">
              <div className="flex items-start gap-3">
                <span className="w-10 h-10 rounded-xl bg-accent-amber/10 text-accent-amber flex items-center justify-center shrink-0">
                  <ShieldAlert size={20} />
                </span>
                <div>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Recommended Action
                  </h2>
                  <p className="mt-1 text-base font-bold text-accent-amber font-mono">
                    {action.action_type}
                  </p>
                  <p className="text-xs text-slate-300 mt-0.5 font-mono">
                    Target: {action.target}
                  </p>
                </div>
              </div>

              {action.rationale && (
                <p className="text-xs text-slate-300 leading-relaxed font-sans">{action.rationale}</p>
              )}

              {action.undo && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                  <Undo2 size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-slate-300">
                    <span className="font-bold text-emerald-400">Reversible.</span> {action.undo}
                  </p>
                </div>
              )}

              <div className="flex items-center gap-2 text-[11px] text-slate-400 pt-1 font-mono">
                <Sparkles size={12} className="text-accent-amber" />
                <span>
                  {analysis?.fallback
                    ? "NOCTRA built-in engine"
                    : `Reasoned by ${analysis?.model ?? "Claude"}`}
                </span>
                {confidencePct !== null && <span>• {confidencePct}% confidence</span>}
              </div>
            </div>
          )}

          {/* Decision Gate Card */}
          <div className="bg-card-bg rounded-2xl border border-card-border p-6 shadow-card">
            {isPending ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-bold text-content-primary">Human Authorization Required</p>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    Approving records the containment action and generates an audit report. You can reverse it anytime.
                  </p>
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <Button variant="secondary" onClick={() => setDialog("decline")} className="flex-1">
                    Decline
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => setDialog("approve")}
                    className="flex-1 bg-accent-amber hover:bg-accent-amber-hover text-app-bg font-bold"
                  >
                    <CheckCircle2 size={16} className="mr-1.5" />
                    Approve
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <span
                    className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                      isApproved ? "bg-emerald-500/15 text-emerald-400" : "bg-app-void text-slate-400"
                    }`}
                  >
                    {isApproved ? <CheckCircle2 size={18} /> : data.decision === "reverted" ? <RotateCcw size={18} /> : <XCircle size={18} />}
                  </span>
                  <div>
                    <p className="text-sm font-bold text-content-primary capitalize">{data.decision}</p>
                    <p className="text-[11px] text-slate-400 font-mono">
                      {data.decided_at ? new Date(data.decided_at).toLocaleString() : "Recorded"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2 border-t border-card-border">
                  {data.report && (
                    <Button variant="ghost" size="sm" onClick={() => setShowReport((s) => !s)} className="text-xs">
                      <FileText size={14} className="mr-1.5" />
                      {showReport ? "Hide Report" : "View Report"}
                    </Button>
                  )}
                  {isApproved && (
                    <Button variant="secondary" size="sm" onClick={() => setDialog("revert")} className="ml-auto text-xs text-red-400">
                      <Undo2 size={14} className="mr-1.5" />
                      Reverse Action
                    </Button>
                  )}
                </div>

                {showReport && data.report && (
                  <pre className="p-4 rounded-xl bg-app-void border border-card-border text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
                    {data.report}
                  </pre>
                )}
              </div>
            )}
          </div>

          {/* Interactive Ask NOCTRA Analyst Copilot Chat */}
          <div className="bg-card-bg rounded-2xl border border-card-border overflow-hidden shadow-card">
            <div className="px-5 py-3.5 border-b border-card-border flex items-center gap-2 bg-app-void">
              <MessageSquare size={16} className="text-accent-amber" />
              <h2 className="text-xs font-bold text-content-primary font-display uppercase tracking-wider">
                Ask NOCTRA Analyst
              </h2>
            </div>

            <div className="p-4 max-h-60 overflow-y-auto space-y-3">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex items-start gap-2 ${
                    msg.sender === "user" ? "flex-row-reverse" : ""
                  }`}
                >
                  <div
                    className={`w-6 h-6 rounded-lg flex items-center justify-center text-[10px] shrink-0 ${
                      msg.sender === "user"
                        ? "bg-accent-amber text-app-bg font-bold"
                        : "bg-app-void text-accent-amber border border-card-border"
                    }`}
                  >
                    {msg.sender === "user" ? <User size={12} /> : <Bot size={12} />}
                  </div>
                  <div
                    className={`max-w-[85%] p-3 rounded-xl text-xs leading-relaxed ${
                      msg.sender === "user"
                        ? "bg-accent-amber/20 text-content-primary border border-accent-amber/30"
                        : "bg-app-void border border-card-border text-slate-300"
                    }`}
                  >
                    <p>{msg.text}</p>
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-400 animate-pulse font-mono">
                  <Bot size={12} className="text-accent-amber" /> NOCTRA is reasoning…
                </div>
              )}
            </div>

            <form onSubmit={handleSendMessage} className="p-3 border-t border-card-border flex gap-2 bg-app-void">
              <input
                type="text"
                placeholder="Ask about blast radius or evidence..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={chatLoading}
                className="flex-1 bg-card-bg border border-card-border rounded-xl px-3 py-2 text-xs text-content-primary placeholder-slate-500 focus:outline-none focus:border-accent-amber"
              />
              <Button type="submit" variant="primary" size="sm" disabled={chatLoading || !chatInput.trim()} className="bg-accent-amber text-app-bg font-bold">
                <Send size={14} />
              </Button>
            </form>
          </div>

        </div>
      </div>

      <ConfirmDialog
        open={dialog === "approve"}
        tone="primary"
        title="Approve this action?"
        message={
          <>
            NOCTRA will record <span className="font-mono font-bold text-accent-amber">{action?.action_type}</span> on{" "}
            <span className="font-mono font-bold text-slate-200">{action?.target}</span> and generate a report. This is reversible anytime.
          </>
        }
        confirmLabel="Approve Action"
        loading={busy}
        onConfirm={() => runDecision("approve")}
        onCancel={() => setDialog(null)}
      />
      <ConfirmDialog
        open={dialog === "decline"}
        tone="danger"
        title="Decline this recommendation?"
        message="The case will be closed with no action taken. It stays on record in your decision feed."
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
        confirmLabel="Reverse Action"
        loading={busy}
        onConfirm={() => runDecision("revert")}
        onCancel={() => setDialog(null)}
      />
    </div>
  );
};

export default CasePage;
