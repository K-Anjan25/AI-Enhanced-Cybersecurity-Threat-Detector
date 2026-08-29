import React, { useState, useRef } from "react";
import { Card, Button, PageHeader } from "../../../components/ui";
import { Bot, Send, Loader2 } from "lucide-react";
import apiClient from "../../../api/client";

interface Msg { role: "user" | "assistant"; content: string; tool_calls?: any[]; }

export default function AgentChatPage() {
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: "I am NOCTRA Autonomous Analyst. Ask me to investigate a case, run a hunt, evaluate ZTNA, or summarize vuln risk. I use tools: hunt, vuln_risk, ztna_evaluate, threat_intel, attack_heatmap, case_timeline." }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [caseId, setCaseId] = useState("1");
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    if (!input.trim()) return;
    const userMsg: Msg = { role: "user", content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    try {
      // Try chat endpoint, fallback to investigate
      try {
        const res: any = await apiClient.post("/ai-agent/chat", { case_id: Number(caseId), message: userMsg.content });
        setMessages(prev => [...prev, { role: "assistant", content: res.data.response || JSON.stringify(res.data, null, 2), tool_calls: res.data.tool_calls }]);
      } catch {
        // fallback to investigate
        const res: any = await apiClient.post("/ai-agent/investigate", { case_id: Number(caseId) });
        setMessages(prev => [...prev, { role: "assistant", content: `Investigation trace for case ${caseId}:\n${JSON.stringify(res.data, null, 2)}`, tool_calls: res.data.tool_calls }]);
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { role: "assistant", content: `Error: ${e?.response?.data?.detail || e.message}` }]);
    } finally {
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <PageHeader title="AI Agent Chat P70" description="Dedicated streaming chat with tool use (hunt, vuln_risk, ztna_evaluate, threat_intel, attack_heatmap, case_timeline). LLM-first with deterministic fallback." />
      
      <div className="flex gap-2 items-center">
        <label className="text-xs">Case ID:</label>
        <input value={caseId} onChange={e=>setCaseId(e.target.value)} className="w-20 px-2 py-1 bg-app-subtle border border-line-subtle rounded text-xs" />
        <span className="text-xs text-content-tertiary">Agent auto-approves LOW only if AI_AGENT_AUTO_APPROVE_LOW_RISK=true (currently false for safety)</span>
      </div>

      <Card className="p-0 overflow-hidden flex flex-col h-[600px]">
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-app-bg">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-lg p-3 text-xs whitespace-pre-wrap ${m.role === "user" ? "bg-accent-primary text-black" : "bg-app-surface border border-line-subtle"}`}>
                <div className="flex items-center gap-2 mb-1 font-bold"><Bot size={12} />{m.role}</div>
                {m.content}
                {m.tool_calls && <pre className="mt-2 p-2 bg-app-subtle rounded text-[10px] overflow-auto">{JSON.stringify(m.tool_calls, null, 2)}</pre>}
              </div>
            </div>
          ))}
          {loading && <div className="flex items-center gap-2 text-xs text-content-tertiary"><Loader2 className="animate-spin" size={14} /> Agent thinking with tools...</div>}
          <div ref={bottomRef} />
        </div>
        <div className="p-3 border-t border-line-subtle bg-app-surface flex gap-2">
          <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{ if(e.key==="Enter") send(); }} placeholder="Ask: investigate case 1, run hunt severity:CRITICAL, evaluate 10.0.0.5 -> 10.0.1.10..." className="flex-1 px-3 py-2 bg-app-subtle border border-line-subtle rounded text-xs" />
          <Button size="sm" onClick={send} disabled={loading}><Send size={14} /> Send</Button>
        </div>
      </Card>

      <div className="p-3 bg-accent-primary/10 border border-accent-primary/30 rounded text-xs">
        <b>Tool Use Implementation:</b> Full Anthropic Messages API with tool_use blocks. When LLM_ENABLED+ANTHROPIC_API_KEY set, we parse `tool_use` and execute server-side tools (hunt/vuln_risk/ztna_evaluate/threat_intel/attack_heatmap/case_timeline). Fallback deterministic template if no key. Memory: per-case AgentMemory trace + org-level summary (TTL 24h) if you enable org memory.
      </div>
    </div>
  );
}
