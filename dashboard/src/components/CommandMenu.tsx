import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Home,
  Inbox,
  ShieldCheck,
  ScrollText,
  TriangleAlert,
  Share2,
  BarChart3,
  LayoutDashboard,
  Workflow,
  ClipboardList,
  UploadCloud,
  Sparkles,
  Search,
  type LucideIcon,
} from "lucide-react";
import AnalystApi from "../api/analystApi";
import type { AnalystCase } from "../types/analyst";
import { BRAND_NAME } from "../constants/brand";

/**
 * NOCTRA Command Menu (⌘K / Ctrl+K).
 * Keyboard-first surface for navigation, jumping to a case, and firing a
 * scenario simulation. Opens via hotkey or the `noctra:command-menu` event
 * (used by the Navbar hint button).
 */

export const COMMAND_MENU_EVENT = "noctra:command-menu";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  group: "Navigate" | "Cases" | "Actions";
  icon: LucideIcon;
  run: () => void;
}

const SIMULATIONS: { key: string; label: string }[] = [
  { key: "credential_leak", label: "Credential leak (T1078)" },
  { key: "phishing_outbreak", label: "Phishing outbreak (T1566)" },
  { key: "data_exfiltration", label: "Data exfiltration (T1048)" },
  { key: "compromised_api_key", label: "Compromised API key (T1098)" },
];

const CommandMenu: React.FC = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [cases, setCases] = useState<AnalystCase[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Hotkey + external open event.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(COMMAND_MENU_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(COMMAND_MENU_EVENT, onOpen);
    };
  }, []);

  // Load the decision feed for case-jump when opening; keep it best-effort.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    setError(null);
    inputRef.current?.focus();
    let alive = true;
    AnalystApi.fetchFeed({ page: 1, limit: 100 })
      .then((res) => {
        if (alive) setCases(Array.isArray(res) ? res : res?.data ?? []);
      })
      .catch(() => {
        if (alive) setCases([]);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  const simulate = async (key: string) => {
    setRunning(key);
    setError(null);
    try {
      const created = await AnalystApi.simulate(key);
      setOpen(false);
      navigate(`/case/${created.id}`);
    } catch {
      setError(`Could not simulate ${key}. Try again from Home.`);
    } finally {
      setRunning(null);
    }
  };

  const items: CommandItem[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const nav: CommandItem[] = [
      { id: "nav-home", label: "Home", hint: "Analyst inbox", group: "Navigate", icon: Home, run: () => go("/") },
      { id: "nav-cases", label: "Cases", hint: "Decision feed", group: "Navigate", icon: Inbox, run: () => go("/feed") },
      { id: "nav-actions", label: "Actions", hint: "Recorded actions log", group: "Navigate", icon: ShieldCheck, run: () => go("/actions") },
      { id: "nav-reports", label: "Reports", hint: "Case outcome reports", group: "Navigate", icon: ScrollText, run: () => go("/reports") },
      { id: "nav-alerts", label: "Alerts", hint: "Raw telemetry", group: "Navigate", icon: TriangleAlert, run: () => go("/alerts") },
      { id: "nav-entities", label: "Entities & Graph", group: "Navigate", icon: Share2, run: () => go("/entities") },
      { id: "nav-analytics", label: "Analytics", group: "Navigate", icon: BarChart3, run: () => go("/analytics") },
      { id: "nav-cockpit", label: "SOC Cockpit", group: "Navigate", icon: LayoutDashboard, run: () => go("/dashboard") },
      { id: "nav-soar", label: "SOAR", hint: "Automation records", group: "Navigate", icon: Workflow, run: () => go("/soar") },
      { id: "nav-incidents", label: "Manual Incidents", group: "Navigate", icon: ClipboardList, run: () => go("/incidents") },
      { id: "nav-logs", label: "Log Uploads", group: "Navigate", icon: UploadCloud, run: () => go("/logs") },
    ];
    const caseItems: CommandItem[] = cases.slice(0, 30).map((c) => ({
      id: `case-${c.id}`,
      label: `Case #${c.id} — ${c.analysis?.headline || c.title}`,
      hint: c.decision,
      group: "Cases" as const,
      icon: Inbox,
      run: () => go(`/case/${c.id}`),
    }));
    const actions: CommandItem[] = SIMULATIONS.map((s) => ({
      id: `sim-${s.key}`,
      label: `Simulate: ${s.label}`,
      hint: "opens the new case",
      group: "Actions" as const,
      icon: Sparkles,
      run: () => simulate(s.key),
    }));
    const all = [...nav, ...caseItems, ...actions];
    if (!q) return all;
    return all.filter((i) => i.label.toLowerCase().includes(q) || (i.hint ?? "").toLowerCase().includes(q));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, cases]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  // Keep the active item in view for arrow-key navigation.
  useEffect(() => {
    listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[active]?.run();
    }
  };

  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${BRAND_NAME} command menu`}
        className="night w-full max-w-xl bg-app-surface rounded-2xl border border-line-bright shadow-overlay overflow-hidden animate-scale-in"
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-line-subtle">
          <Search size={15} className="text-content-tertiary shrink-0" aria-hidden />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-menu-list"
            aria-activedescendant={items[active] ? `cmd-${items[active].id}` : undefined}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search cases, pages, or run a scenario…"
            className="flex-1 bg-transparent text-sm text-content-primary placeholder-content-tertiary focus:outline-none"
          />
          <kbd className="text-[10px] font-mono text-content-tertiary border border-line-subtle rounded px-1.5 py-0.5">esc</kbd>
        </div>

        {error && (
          <p className="px-4 py-2 text-xs text-status-critical" role="alert">
            {error}
          </p>
        )}

        <ul
          ref={listRef}
          id="command-menu-list"
          role="listbox"
          aria-label="Commands"
          className="max-h-[46vh] overflow-y-auto py-2"
        >
          {items.length === 0 && (
            <li className="px-4 py-6 text-center text-xs text-content-tertiary">
              Nothing matches “{query}”.
            </li>
          )}
          {items.map((item, i) => {
            const showGroup = item.group !== lastGroup;
            lastGroup = item.group;
            const Icon = item.icon;
            const isActive = i === active;
            return (
              <React.Fragment key={item.id}>
                {showGroup && (
                  <li aria-hidden className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
                    {item.group}
                  </li>
                )}
                <li
                  id={`cmd-${item.id}`}
                  role="option"
                  aria-selected={isActive}
                  data-active={isActive}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    item.run();
                  }}
                  className={`mx-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm cursor-pointer transition ${
                    isActive ? "bg-accent-primary/15 text-content-primary" : "text-content-secondary"
                  } ${running === item.id.replace("sim-", "") ? "opacity-50 pointer-events-none" : ""}`}
                >
                  <Icon size={14} className={isActive ? "text-accent-secondary" : "text-content-tertiary"} aria-hidden />
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.hint && (
                    <span className="text-[10px] font-mono uppercase tracking-wider text-content-tertiary">{item.hint}</span>
                  )}
                </li>
              </React.Fragment>
            );
          })}
        </ul>

        <div className="flex items-center justify-between px-4 py-2 border-t border-line-subtle text-[10px] text-content-tertiary">
          <span className="font-mono">↑↓ navigate · ↵ open · esc close</span>
          <span className="font-mono">{BRAND_NAME}</span>
        </div>
      </div>
    </div>
  );
};

export default CommandMenu;
