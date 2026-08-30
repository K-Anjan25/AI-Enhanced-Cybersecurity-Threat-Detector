import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ShieldAlert,
  GitBranch,
  Sparkles,
  Undo2,
  FileText,
  Download,
  CheckCircle2,
  XCircle,
  RotateCcw,
  MessageSquare,
  Send,
  Bot,
  User,
  TriangleAlert,
} from "lucide-react";
import {
  PageHeader,
  Card,
  Button,
  SeverityBadge,
  StatusBadge,
  ConfirmDialog,
  EmptyState,
  SkeletonChart,
  ThinkingIndicator,
  Term,
} from "../../../components/ui";
import AnalystApi from "../../../api/analystApi";
import { api } from "../../../api/axios";
import { fetchAlerts } from "../../../api/alertApi";
import type { Alert } from "../../../types/alert";
import type { AnalystCase, BlastNode, Decision, ChatMessage, TimelineEntry } from "../../../types/analyst";
import { getApiError } from "../../../utils/getApiError";
import CaseImpact from "../../../components/CaseImpact";

type DialogKind = "approve" | "decline" | "revert" | null;

const DECISION_BADGE: Record<Decision, { tone: "success" | "warning" | "critical" | "neutral"; label: string }> = {
  pending: { tone: "warning", label: "Awaiting your decision" },
  approved: { tone: "success", label: "Approved" },
  declined: { tone: "neutral", label: "Declined" },
  reverted: { tone: "neutral", label: "Reverted" },
};

/** Timeline entry dots — kind-colored, never meaning-critical (label carries it). */
const TIMELINE_DOT: Record<string, string> = {
  evidence: "text-accent-secondary",
  opened: "text-accent-primary",
  action_recorded: "text-status-success",
  decision: "text-status-success",
  report: "text-content-tertiary",
  chat: "text-content-tertiary",
};

/** Clock text for timeline entries — never "Invalid Date". */
const fmtTime = (iso?: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? "—"
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
  const [exportingPdf, setExportingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // Evidence state — the raw source alert linked to this case (observed fact).
  const [evidence, setEvidence] = useState<Alert | null>(null);

  // Server-side case record (timeline) — composed by the backend from real
  // rows only; hidden if unavailable rather than fabricated client-side.
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);

  const loadCase = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const c = await AnalystApi.fetchCase(id);
      setData(c);
      // Seed initial welcome message from the NOCTRA analyst.
      setChatMessages([
        {
          id: "welcome",
          sender: "axiom",
          text: `Hello! I am your NOCTRA analyst. Ask me anything about Case #${c.id} (${c.title}).`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } catch (err: any) {
      setError(err?.response?.status === 404 ? "That case doesn't exist." : getApiError(err, "Failed to load the case"));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  // Case record timeline — refetch when the case identity or its decision
  // state changes (approve/revert updates the entries).
  useEffect(() => {
    let alive = true;
    if (!data?.id) {
      setTimeline([]);
      return;
    }
    AnalystApi.fetchTimeline(data.id)
      .then((res) => {
        if (alive) setTimeline(res.entries ?? []);
      })
      .catch(() => {
        if (alive) setTimeline([]);
      });
    return () => {
      alive = false;
    };
  }, [data?.id, data?.decision, data?.decided_at]);

  // Resolve the linked source alert for the evidence panel (best-effort: the
  // alert list is the only read surface; missing rows are stated honestly).
  useEffect(() => {
    let alive = true;
    const alertId = data?.source_alert_id;
    if (!alertId) {
      setEvidence(null);
      return;
    }
    fetchAlerts(1, 100)
      .then((items) => {
        if (alive) setEvidence(items.find((a) => a.id === alertId) ?? null);
      })
      .catch(() => {
        if (alive) setEvidence(null);
      });
    return () => {
      alive = false;
    };
  }, [data?.source_alert_id]);

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
      const res: any = await AnalystApi.chatAboutCase(id, userText);
      const analystMsg: ChatMessage = {
        id: `n-${Date.now()}`,
        sender: "axiom",
        text: res.answer + (res.llm_used ? "" : ""),
        confidence: res.confidence,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + (res.llm_used ? " · LLM" : ""),
      };
      setChatMessages((prev) => [...prev, analystMsg]);
    } catch (err: any) {
      const is429 = err?.response?.status === 429;
      const detail = err?.response?.data?.detail || "";
      setChatMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          sender: "axiom",
          text: is429 ? `Rate limited — ${detail}. Try again shortly.` : "I couldn't process that question right now. Please try again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleExportPdf = async () => {
    if (!data?.id) return;
    setExportingPdf(true);
    setPdfError(null);
    try {
      const resp = await api.get(`/analyst/cases/${data.id}/report.pdf`, { responseType: "blob" });
      const blob = new Blob([resp.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `noctra-case-${data.id}-report.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 409) setPdfError("No report yet — a report is written when a decision is recorded.");
      else if (status === 501) setPdfError("PDF export is not available on this server (reportlab is not installed).");
      else setPdfError("Could not export PDF. Try again.");
    } finally {
      setExportingPdf(false);
    }
  };

  const handleExportEvidencePdf = async (includeSoc2 = false) => {
    if (!data?.id) return;
    setExportingPdf(true);
    setPdfError(null);
    try {
      const resp = await api.get(`/compliance/cases/${data.id}/evidence-bundle/pdf`, {
        responseType: "blob",
        params: { include_soc2: includeSoc2 },
      });
      const blob = new Blob([resp.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `evidence-bundle-case-${data.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      const status = err?.response?.status;
      if (status === 501) setPdfError("Evidence PDF export needs reportlab on server.");
      else setPdfError("Could not export evidence bundle PDF.");
    } finally {
      setExportingPdf(false);
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
      setError(getApiError(err, `Could not ${kind} this case`));
    } finally {
      setBusy(false);
    }
  };

  const nodeById = useMemo(() => {
    const map = new Map<number, BlastNode>();
    (data?.blast_radius?.nodes ?? []).forEach((n) => map.set(n.id, n));
    return map;
  }, [data]);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in bg-app-bg min-h-screen -m-6 p-6 sm:p-8">
        <PageHeader
          title="Case"
          backTo="/feed"
          crumbs={[{ label: "Decisions", to: "/feed" }, { label: "Case" }]}
        />
        <SkeletonChart className="h-56" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <SkeletonChart className="lg:col-span-2 h-72" />
          <SkeletonChart className="h-72" />
        </div>
      </div>
    );
  }

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
        <div
          role="alert"
          className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-sm text-status-critical font-medium"
        >
          {error}
        </div>
      )}

      {/* NOCTRA's assessment — inferred, never presented as confirmed fact. */}
      <div className="bg-app-surface rounded-2xl border border-line-subtle p-6 shadow-card space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-content-tertiary">
            NOCTRA&rsquo;s assessment
          </h2>
          <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-app-subtle text-content-secondary border border-line-subtle">
            Inferred — not confirmed fact
          </span>
        </div>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-content-tertiary mb-1">
            What happened
          </h3>
          <p className="text-content-primary leading-relaxed font-medium">{analysis?.what_happened || data.description}</p>
        </div>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-content-tertiary mb-1">
            Why it matters
          </h3>
          <p className="text-content-secondary leading-relaxed">{analysis?.why_it_matters}</p>
        </div>

        {/* Org-specific impact, joined from the attack-path, posture and
            exposure modules. Renders nothing when those have no real data. */}
        <CaseImpact context={data.context} className="pt-1" />
      </div>

      {/* Evidence — the observed source alert, on the night canvas. */}
      {data.source_alert_id && (
        <div className="night console-panel text-content-primary rounded-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-line-bright flex items-center gap-2">
            <TriangleAlert size={16} className="text-accent-secondary" aria-hidden />
            <h2 className="text-sm font-bold text-content-primary font-display tracking-tight">Evidence</h2>
            <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-app-subtle/80 text-content-secondary border border-line-bright">
              Observed
            </span>
            <span className="text-xs text-content-tertiary ml-auto font-mono">
              Linked alert #{data.source_alert_id}
            </span>
          </div>
          {evidence ? (
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Type</p>
                  <p className="text-xs font-mono text-content-primary mt-0.5">{evidence.alert_type || "—"}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Severity</p>
                  <div className="mt-0.5">
                    <SeverityBadge severity={String(evidence.severity || "LOW")} />
                  </div>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Source IP</p>
                  <p className="text-xs font-mono text-content-primary mt-0.5">{evidence.source_ip || "—"}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
                    <Term>MITRE</Term>
                  </p>
                  <p className="text-xs font-mono text-content-primary mt-0.5">
                    <Term mono>{evidence.mitre_technique_id || "—"}</Term>
                  </p>
                </div>
              </div>
              <pre className="p-3 rounded-xl bg-app-void text-content-secondary border border-line-bright text-xs whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
                {evidence.message || "(no raw message recorded)"}
              </pre>
            </div>
          ) : (
            <p className="px-5 py-4 text-xs text-content-tertiary">
              Linked to alert #{data.source_alert_id} — the raw alert is no longer present in the current
              alert list, so its details cannot be shown.
            </p>
          )}
        </div>
      )}

      {/* Blast radius — night canvas. Observed evidence, not inference. */}
      <div className="night console-panel text-content-primary rounded-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-line-bright flex items-center gap-2">
          <GitBranch size={16} className="text-accent-secondary" aria-hidden />
          <h2 className="text-sm font-bold text-content-primary font-display tracking-tight">
            <Term>Blast radius</Term> — affected assets
          </h2>
          <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-app-subtle/80 text-content-secondary border border-line-bright">
            Observed
          </span>
          <span className="text-xs text-content-tertiary ml-auto font-mono">
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
                className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl border border-line-bright bg-app-void/80"
              >
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-app-subtle text-content-secondary border border-line-bright shrink-0">
                  {n.entity_type}
                </span>
                <span className="text-xs text-content-secondary font-mono truncate" title={n.value}>
                  {n.value}
                </span>
                {isRoot && (
                  <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-accent-secondary shrink-0">
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
                <span className="text-accent-secondary"> —{l.relation}→ </span>
                {nodeById.get(l.target)?.value ?? l.target}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Recommended action — the one thing on this page that needs a human,
          so it is the one element carrying HUD corner brackets (spec §40.4:
          brackets mark the focal element of a view, never decoration). */}
      {action && (
        <div className="hud-corners bg-app-surface rounded-2xl border border-accent-primary/30 p-6 shadow-card">
          <div className="flex items-start gap-3">
            <span className="w-10 h-10 rounded-xl bg-accent-primary/15 text-accent-primary flex items-center justify-center shrink-0">
              <ShieldAlert size={20} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-content-tertiary flex items-center gap-2">
                  NOCTRA recommends
                  <span className="text-[10px] font-mono normal-case tracking-wider px-2 py-0.5 rounded bg-app-subtle text-content-secondary border border-line-subtle">
                    Recommendation
                  </span>
                </h2>
                <p className="mt-1 text-lg font-bold text-content-primary font-display">
                  <Term mono>{action.action_type}</Term>
                </p>
                <p className="text-sm text-content-secondary mt-0.5">
                  Target: <span className="font-mono text-content-primary font-bold">{action.target}</span>
                </p>
              </div>
              {action.rationale && (
                <p className="text-sm text-content-secondary leading-relaxed">{action.rationale}</p>
              )}
              {action.undo && (
                  <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-status-success/10 border border-status-success/30">
                  <Undo2 size={15} className="text-status-success mt-0.5 shrink-0" aria-hidden />
                  <p className="text-xs text-content-secondary">
                    <span className="font-bold text-status-success"><Term>Reversible</Term>.</span> {action.undo}
                  </p>
                </div>
              )}
              <div className="flex items-center gap-3 text-xs text-content-tertiary pt-1">
                <span className="inline-flex items-center gap-1 font-medium">
                  <Sparkles size={12} className="text-accent-primary" aria-hidden />
                  {analysis?.fallback
                    ? "NOCTRA built-in reasoning engine"
                    : `Reasoned by ${analysis?.model ?? "Claude"}`}
                </span>
                {confidencePct !== null && (
                  <span>
                    · <Term>confidence</Term> {confidencePct}%
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Ask NOCTRA — interactive analyst chat (night canvas) */}
      <div className="night console-panel text-content-primary rounded-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-line-bright flex items-center gap-2 bg-app-void/60">
          <MessageSquare size={16} className="text-accent-secondary" />
          <h2 className="text-sm font-bold text-content-primary font-display tracking-tight">
            Ask NOCTRA
          </h2>
          <span className="text-xs text-content-tertiary ml-auto font-mono">
            Interactive Q&amp;A
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
                    ? "bg-accent-primary text-brand-ink"
                    : "bg-app-subtle text-accent-secondary border border-line-bright"
                }`}
              >
                {msg.sender === "user" ? <User size={14} /> : <Bot size={14} />}
              </div>
              <div
                className={`max-w-[80%] p-3 rounded-xl text-xs leading-relaxed ${
                  msg.sender === "user"
                    ? "bg-accent-primary text-brand-ink"
                    : "bg-app-void border border-line-bright text-content-secondary"
                }`}
              >
                <p>{msg.text}</p>
                <div className="mt-1 flex items-center justify-between text-[10px] text-content-tertiary font-mono">
                  <span>{msg.timestamp}</span>
                  {msg.confidence != null && (
                    <span>Confidence: {Math.round(Number(msg.confidence) * 100)}%</span>
                  )}
                </div>
              </div>
            </div>
          ))}
          {chatLoading && (
            /* Spec §30: AI reasoning is a three-dot shimmer — never a pulsing
               block of text, never a glow storm. */
            <ThinkingIndicator label="NOCTRA is reasoning" className="px-1 py-1" />
          )}
        </div>

        <form onSubmit={handleSendMessage} className="p-3 border-t border-line-bright flex gap-2 bg-app-void">
          <input
            type="text"
            placeholder="Ask about blast radius, threat actor, or remediation details..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            disabled={chatLoading}
            className="flex-1 bg-app-subtle border border-line-bright rounded-xl px-3 py-2 text-xs text-content-primary placeholder-content-tertiary focus:outline-none focus:border-accent-primary"
          />
          <Button type="submit" variant="primary" size="sm" disabled={chatLoading || !chatInput.trim()}>
            <Send size={14} />
          </Button>
        </form>
      </div>

      {/* Decision gate */}
      <div className="bg-app-surface rounded-2xl border border-line-subtle p-6 shadow-card space-y-4">
        {isPending ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-content-primary">This one's your call.</p>
              <p className="text-xs text-content-tertiary mt-0.5">
                Approving records the action and generates a report. You can reverse it afterwards.
              </p>
              <p className="text-[11px] text-content-tertiary font-mono mt-1">
                Case opened {data.created_at ? new Date(data.created_at).toLocaleString() : "—"} · waiting on your decision
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="ghost"
                onClick={async () => {
                  try {
                    const exp = await AnalystApi.exportCase(data.id);
                    const blob = new Blob([JSON.stringify(exp, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `noctra-case-${data.id}-export.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch {}
                }}
              >
                <FileText size={16} className="mr-1.5" aria-hidden />
                Export JSON
              </Button>
              <Button variant="ghost" onClick={handleExportPdf} disabled={exportingPdf}>
                <Download size={16} className="mr-1.5" aria-hidden />
                {exportingPdf ? "Exporting…" : "Export PDF"}
              </Button>
              <Button variant="ghost" onClick={() => handleExportEvidencePdf(false)} disabled={exportingPdf}>
                <Download size={16} className="mr-1.5" aria-hidden />
                Evidence PDF
              </Button>
              <Button variant="secondary" onClick={() => setDialog("decline")}>
                Decline
              </Button>
              <Button variant="primary" onClick={() => setDialog("approve")}>
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
                  isApproved ? "bg-status-success/15 text-status-success" : "bg-app-subtle text-content-secondary"
                }`}
              >
                {isApproved ? <CheckCircle2 size={18} aria-hidden /> : data.decision === "reverted" ? <RotateCcw size={18} aria-hidden /> : <XCircle size={18} aria-hidden />}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold text-content-primary capitalize">{data.decision}</p>
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
              <div className="flex items-center gap-2 ml-auto shrink-0 flex-wrap">
                <Button
                  variant="ghost"
                  onClick={async () => {
                    try {
                      const exp = await AnalystApi.exportCase(data.id);
                      const blob = new Blob([JSON.stringify(exp, null, 2)], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `noctra-case-${data.id}-export.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch {}
                  }}
                >
                  <FileText size={16} className="mr-1.5" aria-hidden />
                  Export JSON
                </Button>
                <Button variant="ghost" onClick={handleExportPdf} disabled={exportingPdf}>
                  <Download size={16} className="mr-1.5" aria-hidden />
                  {exportingPdf ? "Exporting…" : "Export PDF"}
                </Button>
                <Button variant="ghost" onClick={() => handleExportEvidencePdf(false)} disabled={exportingPdf}>
                  <Download size={16} className="mr-1.5" aria-hidden />
                  Evidence PDF
                </Button>
                <Button variant="ghost" onClick={() => handleExportEvidencePdf(true)} disabled={exportingPdf}>
                  <Download size={16} className="mr-1.5" aria-hidden />
                  Evidence+SOC2 PDF
                </Button>
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
              <pre className="night console-panel p-4 rounded-sm text-content-secondary text-xs whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
                {data.report}
              </pre>
            )}
          </div>
        )}

        {pdfError && (
          <div role="status" className="px-4 py-2 rounded-lg bg-status-warning/10 border border-status-warning/30 text-xs text-content-primary">
            {pdfError}
          </div>
        )}

        {/* Case record — server-composed from real rows only (evidence, open,
            decision, recorded action, report, audit). */}
        {timeline.length > 0 && (
          <div className="pt-1 border-t border-line-subtle">
            <p className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary mb-2 mt-3">
              Case record
            </p>
            <ol className="space-y-1.5">
              {timeline.map((entry, i) => (
                <li
                  key={`${entry.kind}-${i}`}
                  className="flex items-baseline gap-2 text-xs text-content-secondary"
                >
                  <span className={TIMELINE_DOT[entry.kind] ?? "text-content-tertiary"} aria-hidden>
                    ●
                  </span>
                  <span className="min-w-0">
                    {entry.label}
                    {entry.detail ? (
                      <span className="text-content-tertiary"> — {entry.detail}</span>
                    ) : null}
                  </span>
                  <span className="text-content-tertiary font-mono ml-auto shrink-0">
                    {fmtTime(entry.at)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={dialog === "approve"}
        tone="primary"
        title="Approve this action?"
        message={
          <>
            NOCTRA will record <span className="font-mono font-bold">{action?.action_type}</span> on{" "}
            <span className="font-mono font-bold">{action?.target}</span> and generate a report. This is{" "}
            <Term>reversible</Term> — it is <Term>record-only</Term>.
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
