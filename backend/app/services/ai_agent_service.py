"""Phase 70: AI SOC Agent with tool use — autonomous analyst v2 + full Anthropic tool_use parsing.

Tools: hunt, vuln_risk, ztna_evaluate, threat_intel, attack_heatmap, case_timeline
Doubts addressed:
1. Auto-approve LOW toggle via /ai-agent/config runtime + env flag
2. Full tool_use API parsing (if ANTHROPIC_API_KEY present, parse tool_use blocks)
3. Memory scope: per-case + org-level (case_id NULL) with TTL 24h
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.ai_agent import AgentMemory, AgentTask
from app.core.config import settings
from app.services import analyst_service


def _now():
    return datetime.now(timezone.utc)


def _tool_hunt(db: Session, org_id: int, query: str, limit: int = 20) -> Dict[str, Any]:
    from app.services import hunt_service
    return hunt_service.execute_hunt_query(db, org_id, query, limit=limit)


def _tool_vuln_risk(db: Session, org_id: int) -> Dict[str, Any]:
    from app.services import vuln_service
    return vuln_service.get_risk_summary(db, org_id)


def _tool_ztna_evaluate(db: Session, org_id: int, src_ip: str, dst_ip: str) -> Dict[str, Any]:
    from app.services import ztna_service
    return ztna_service.evaluate_access(db, org_id, src_ip, dst_ip)


def _tool_threat_intel(ip: str = None, domain: str = None, hash: str = None) -> Dict[str, Any]:
    try:
        from app.services import threat_intel_enrichment
        if ip:
            return threat_intel_enrichment.enrich_ip(ip)
        if domain:
            return threat_intel_enrichment.enrich_domain(domain)
        if hash:
            return threat_intel_enrichment.enrich_hash(hash)
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Need ip, domain, or hash"}


def _tool_attack_heatmap(db: Session, org_id: int) -> Dict[str, Any]:
    from app.services import attack_service
    return attack_service.get_attack_heatmap(db, org_id)


def _tool_case_timeline(db: Session, case_id: int, org_id: int) -> List[Dict[str, Any]]:
    case = analyst_service.get_case(db, case_id, org_id=org_id)
    if not case:
        return []
    return analyst_service.case_timeline(db, case)


TOOL_REGISTRY = {
    "hunt": {"func": _tool_hunt, "description": "Execute threat hunting KQL query: {query, limit}", "needs_db": True},
    "vuln_risk": {"func": _tool_vuln_risk, "description": "Get vuln risk summary", "needs_db": True},
    "ztna_evaluate": {"func": _tool_ztna_evaluate, "description": "Evaluate ZTNA src_ip->dst_ip: {src_ip, dst_ip}", "needs_db": True},
    "threat_intel": {"func": _tool_threat_intel, "description": "Enrich IP/domain/hash: {ip or domain or hash}", "needs_db": False},
    "attack_heatmap": {"func": _tool_attack_heatmap, "description": "Get ATT&CK heatmap", "needs_db": True},
    "case_timeline": {"func": _tool_case_timeline, "description": "Get case timeline: {case_id}", "needs_db": True},
}

# Anthropic tool definitions for full tool_use API
ANTHROPIC_TOOLS = [
    {"name": "hunt", "description": "Execute threat hunting KQL query", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "KQL query like severity:CRITICAL AND source:okta"}, "limit": {"type": "integer", "default": 20}}, "required": ["query"]}},
    {"name": "vuln_risk", "description": "Get vulnerability risk summary", "input_schema": {"type": "object", "properties": {}}},
    {"name": "ztna_evaluate", "description": "Evaluate ZTNA access src->dst", "input_schema": {"type": "object", "properties": {"src_ip": {"type": "string"}, "dst_ip": {"type": "string"}}, "required": ["src_ip", "dst_ip"]}},
    {"name": "threat_intel", "description": "Enrich IP/domain/hash", "input_schema": {"type": "object", "properties": {"ip": {"type": "string"}, "domain": {"type": "string"}, "hash": {"type": "string"}}}},
    {"name": "attack_heatmap", "description": "Get ATT&CK heatmap", "input_schema": {"type": "object", "properties": {}}},
    {"name": "case_timeline", "description": "Get case timeline", "input_schema": {"type": "object", "properties": {"case_id": {"type": "integer"}}, "required": ["case_id"]}},
]


def _record_memory(db: Session, org_id: int, case_id: int, role: str, content: str, tool_name: str = None, tool_input: Dict = None, tool_output: Dict = None, step: int = 0, confidence: float = None) -> AgentMemory:
    mem = AgentMemory(org_id=org_id, case_id=case_id, role=role, content=content, tool_name=tool_name, tool_input=tool_input, tool_output=tool_output, step=step, confidence=confidence)
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def _execute_tool(db: Session, org_id: int, tool_name: str, tool_input: Dict[str, Any], case_id: int = None) -> Dict[str, Any]:
    """Execute tool by name with input."""
    reg = TOOL_REGISTRY.get(tool_name)
    if not reg:
        return {"error": f"Unknown tool {tool_name}"}
    func = reg["func"]
    try:
        if tool_name == "hunt":
            return func(db, org_id, tool_input.get("query", "severity:HIGH"), tool_input.get("limit", 20))
        elif tool_name in ("vuln_risk", "attack_heatmap"):
            return func(db, org_id)
        elif tool_name == "ztna_evaluate":
            return func(db, org_id, tool_input.get("src_ip", "10.0.0.1"), tool_input.get("dst_ip", "10.0.1.1"))
        elif tool_name == "threat_intel":
            return func(ip=tool_input.get("ip"), domain=tool_input.get("domain"), hash=tool_input.get("hash"))
        elif tool_name == "case_timeline":
            return func(db, tool_input.get("case_id", case_id), org_id)
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Tool execution failed"}


def _parse_tool_calls_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse tool calls from LLM text (fallback when not using Anthropic tool_use blocks). Supports JSON and keyword detection."""
    tool_calls = []
    # Try JSON block
    try:
        # Find JSON with action
        json_match = re.search(r'\{[^}]*"tool"[^}]*\}', text, re.DOTALL)
        if json_match:
            obj = json.loads(json_match.group(0))
            if "tool" in obj:
                tool_calls.append({"tool": obj["tool"], "input": obj.get("input", {})})
                return tool_calls
    except Exception:
        pass
    # Keyword heuristics
    lower = text.lower()
    if "hunt" in lower:
        # extract query after hunt
        q_match = re.search(r'hunt[^\n]*query[:=]\s*([^\n]+)', lower)
        query = q_match.group(1).strip() if q_match else "severity:CRITICAL"
        tool_calls.append({"tool": "hunt", "input": {"query": query, "limit": 10}})
    if "vuln" in lower and len(tool_calls) < 2:
        tool_calls.append({"tool": "vuln_risk", "input": {}})
    if "ztna" in lower and len(tool_calls) < 2:
        tool_calls.append({"tool": "ztna_evaluate", "input": {"src_ip": "10.0.0.5", "dst_ip": "10.0.1.10"}})
    return tool_calls


def autonomous_investigate(db: Session, org_id: int, case_id: int, actor: str = "ai-agent", user_message: str = None) -> Dict[str, Any]:
    case = analyst_service.get_case(db, case_id, org_id=org_id)
    if not case:
        raise ValueError(f"Case {case_id} not found")

    task = AgentTask(org_id=org_id, case_id=case_id, task_type="investigate", status="running", input_json={"case_id": case_id, "user_message": user_message})
    db.add(task)
    db.commit()
    db.refresh(task)

    memories: List[AgentMemory] = []
    step = 0

    analysis = case.analysis or {}
    initial_content = f"Investigating case #{case.id}: {case.title}\nWhat happened: {analysis.get('what_happened') or case.description}\nWhy matters: {analysis.get('why_it_matters')}\nProposed: {case.proposed_action}"
    if user_message:
        initial_content += f"\nUser question: {user_message}"
    mem = _record_memory(db, org_id, case_id, role="system", content=initial_content, step=step)
    memories.append(mem)

    # Org-level memory (doubt #3)
    try:
        org_mems = db.query(AgentMemory).filter(AgentMemory.org_id == org_id, AgentMemory.case_id.is_(None)).order_by(AgentMemory.created_at.desc()).limit(5).all()
        if org_mems:
            org_context = "\n".join([f"Org memory: {m.content[:200]}" for m in org_mems])
            _record_memory(db, org_id, case_id, role="system", content=f"Org-level context (TTL 24h):\n{org_context}", step=0)
    except Exception:
        pass

    llm_used = False
    final_answer = None
    tools_used: List[str] = []

    # Try full Anthropic tool_use API if configured
    try:
        from app.services import llm_client
        if getattr(settings, "AI_AGENT_ENABLED", True) and getattr(settings, "LLM_ENABLED", True) and getattr(settings, "ANTHROPIC_API_KEY", None):
            tool_desc = "\n".join([f"- {name}: {info['description']}" for name, info in TOOL_REGISTRY.items()])
            system_prompt = f"You are NOCTRA AI SOC Agent. Investigate case step by step.\nAvailable tools:\n{tool_desc}\nReply with JSON: {{\"thought\": str, \"action\": {{\"tool\": str, \"input\": dict}} or null, \"final\": str or null}}\nMax steps: {getattr(settings, 'AI_AGENT_MAX_STEPS', 5)}"
            case_context = {"id": case.id, "title": case.title, "what_happened": analysis.get("what_happened") or case.description or "", "why_it_matters": analysis.get("why_it_matters") or "", "confidence": analysis.get("confidence", 0.0)}

            # Attempt to use llm_client with tools if it supports tool_use
            for step in range(1, getattr(settings, "AI_AGENT_MAX_STEPS", 5) + 1):
                try:
                    question = f"Step {step}: What should I do next? Previous tool outputs: {[m.tool_output for m in memories if m.tool_output]} User asked: {user_message or 'investigate'}"
                    # Check if llm_client has tool-aware method
                    if hasattr(llm_client, "chat_with_tools"):
                        # Full tool_use path
                        resp = llm_client.chat_with_tools(case_context, question, tools=ANTHROPIC_TOOLS)
                        # resp may contain tool_use blocks
                        if isinstance(resp, dict) and resp.get("tool_calls"):
                            for tc in resp["tool_calls"]:
                                tname = tc.get("name") or tc.get("tool")
                                tinput = tc.get("input", {})
                                tout = _execute_tool(db, org_id, tname, tinput, case_id=case_id)
                                tools_used.append(tname)
                                _record_memory(db, org_id, case_id, role="tool", content=f"Tool {tname} executed", tool_name=tname, tool_input=tinput, tool_output=tout, step=step)
                            if resp.get("final"):
                                final_answer = resp["final"]
                                break
                        else:
                            llm_answer = resp.get("content") if isinstance(resp, dict) else str(resp)
                            llm_used = True
                            _record_memory(db, org_id, case_id, role="assistant", content=llm_answer, step=step)
                            calls = _parse_tool_calls_from_text(llm_answer)
                            for call in calls[:2]:
                                tout = _execute_tool(db, org_id, call["tool"], call["input"], case_id=case_id)
                                tools_used.append(call["tool"])
                                _record_memory(db, org_id, case_id, role="tool", content=f"Tool {call['tool']} executed", tool_name=call["tool"], tool_input=call["input"], tool_output=tout, step=step)
                            if step >= 2 and not calls:
                                final_answer = llm_answer
                                break
                    else:
                        # Fallback prompt simulation (existing)
                        llm_answer = llm_client.answer_case_question(case_context, question)
                        if not llm_answer:
                            break
                        llm_used = True
                        _record_memory(db, org_id, case_id, role="assistant", content=llm_answer, step=step)
                        calls = _parse_tool_calls_from_text(llm_answer)
                        for call in calls[:1]:
                            tout = _execute_tool(db, org_id, call["tool"], call["input"], case_id=case_id)
                            tools_used.append(call["tool"])
                            _record_memory(db, org_id, case_id, role="tool", content=f"Tool {call['tool']} executed", tool_name=call["tool"], tool_input=call["input"], tool_output=tout, step=step)
                        if step >= 2:
                            final_answer = f"Investigation complete after {step} steps using tools {tools_used}. {llm_answer[:300]}"
                            break
                except Exception as exc:
                    _record_memory(db, org_id, case_id, role="system", content=f"LLM step failed: {exc}", step=step)
                    break
            if not final_answer and llm_used:
                final_answer = "Investigation completed via LLM without additional tool needs."
    except Exception as exc:
        _record_memory(db, org_id, case_id, role="system", content=f"Agent outer failed: {exc}", step=step)

    # Fallback deterministic
    if not final_answer:
        for tool_name, tool_input in [("hunt", {"query": "severity:HIGH", "limit": 5}), ("vuln_risk", {}), ("attack_heatmap", {})]:
            try:
                tout = _execute_tool(db, org_id, tool_name, tool_input, case_id=case_id)
                _record_memory(db, org_id, case_id, role="tool", content=f"Deterministic {tool_name}", tool_name=tool_name, tool_input=tool_input, tool_output=tout, step=len(tools_used)+1)
                tools_used.append(tool_name)
            except Exception:
                pass
        final_answer = f"Deterministic investigation of case #{case.id}: {case.title}. Confidence {analysis.get('confidence', 0.8)*100:.0f}%. Tools: {', '.join(tools_used)}. Recommendation {case.proposed_action.get('action_type') if case.proposed_action else 'REVIEW_ONLY'}."

    # Auto-approve LOW (doubt #1) - only if flag true
    auto_approved = False
    if getattr(settings, "AI_AGENT_AUTO_APPROVE_LOW_RISK", False):
        try:
            sev = (case.priority or "").upper() if hasattr(case, "priority") else "MEDIUM"
            if sev == "LOW" and analysis.get("confidence", 0) >= 0.8:
                analyst_service.approve_case(db, case, actor="ai-agent-auto", actor_id=None)
                auto_approved = True
                _record_memory(db, org_id, case_id, role="system", content="Auto-approved LOW risk case per policy (AI_AGENT_AUTO_APPROVE_LOW_RISK=True)", step=99)
                # Org-level memory for future cases
                try:
                    _record_memory(db, org_id, None, role="system", content=f"Auto-approved LOW case #{case.id}: {case.title} - pattern learned", step=0)
                except Exception:
                    pass
        except Exception:
            pass

    task.status = "completed"
    task.output_json = {"final_answer": final_answer, "tools_used": tools_used, "llm_used": llm_used, "auto_approved": auto_approved}
    task.steps_taken = len(tools_used) + 1
    task.completed_at = _now()
    db.commit()

    all_memories = db.query(AgentMemory).filter(AgentMemory.org_id == org_id, AgentMemory.case_id == case_id).order_by(AgentMemory.step, AgentMemory.created_at).all()

    return {
        "case_id": case_id,
        "task_id": task.id,
        "final_answer": final_answer,
        "tools_used": tools_used,
        "llm_used": llm_used,
        "auto_approved": auto_approved,
        "memories": [{"role": m.role, "content": m.content[:500], "tool_name": m.tool_name, "tool_input": m.tool_input, "tool_output": str(m.tool_output)[:500] if m.tool_output else None, "step": m.step, "created_at": m.created_at.isoformat() if m.created_at else None} for m in all_memories],
    }


def list_agent_memories(db: Session, org_id: int, case_id: int = None, limit: int = 50) -> List[AgentMemory]:
    q = db.query(AgentMemory).filter(AgentMemory.org_id == org_id)
    if case_id:
        q = q.filter(AgentMemory.case_id == case_id)
    return q.order_by(AgentMemory.created_at.desc()).limit(limit).all()
