import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Inbox, X } from "lucide-react";
import AnalystApi from "../../api/analystApi";
import type { AnalystCase } from "../../types/analyst";
import { EVENTS, emit } from "../../lib/events";
import { useNoctraEvent, useHotkey } from "../../hooks";
import { cn, SeverityBadge } from "../ui";

/**
 * PendingDecisionsDrawer — the WooCommerce mini-cart pattern applied to a
 * security analyst product: a non-blocking slide-out drawer that lists what
 * needs the human right now (pending cases), with one clear path forward
 * ("Review & decide"). Refreshes on approve/decline elsewhere via the event
 * bus, so the count pill and the drawer never disagree.
 *
 * Honest empty state: "Nothing needs you right now." — never "NO DATA".
 */

const timeAgo = (iso?: string | null): string => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
};

const PendingDecisionsDrawer: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<AnalystCase[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await AnalystApi.fetchFeed({ page: 1, limit: 20 });
      const items = (res.data ?? []).filter((c) => c.decision === "pending");
      setPending(items);
      emit(EVENTS.PENDING_CHANGED, items.length);
    } catch {
      /* keep last-known list; the drawer stays usable */
    } finally {
      setLoading(false);
    }
  }, []);

  // Open via the event bus (Navbar trigger, ⌘K, anywhere in the app).
  useNoctraEvent(EVENTS.OPEN_PENDING_DRAWER, () => setOpen(true));
  useNoctraEvent(EVENTS.CLOSE_PENDING_DRAWER, () => setOpen(false));
  // Refresh when a decision is made elsewhere (case page, bell menu…).
  useNoctraEvent(EVENTS.PENDING_CHANGED, () => refresh(true));

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  // Escape closes. (⌘K is reserved for the command menu.)
  useHotkey("escape", () => setOpen(false));

  // Lock body scroll while the drawer is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Focus the panel when it opens (a11y).
  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  const close = () => setOpen(false);

  const goCase = (id: number) => {
    close();
    navigate(`/case/${id}`);
  };

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          aria-hidden
          onClick={close}
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] animate-fade-in"
        />
      )}

      {/* Panel */}
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Pending decisions"
        tabIndex={-1}
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-full sm:w-[26rem] bg-white border-l border-black/5 shadow-overlay flex flex-col outline-none transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 h-16 border-b border-black/5 shrink-0">
          <div className="w-8 h-8 rounded-full bg-brand-gradient-soft border border-accent-primary/20 flex items-center justify-center">
            <Inbox size={15} className="text-accent-secondary" aria-hidden />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-bold font-display tracking-tight text-neutral-900">
              Pending decisions
            </h2>
            <p className="text-[11px] text-neutral-400">
              {loading ? "Reading the brief…" : `${pending.length} case${pending.length === 1 ? "" : "s"} waiting on you`}
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close pending decisions"
            className="ml-auto w-9 h-9 rounded-full bg-neutral-100 border border-black/5 text-neutral-500 hover:text-neutral-900 transition flex items-center justify-center cursor-pointer"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto min-h-0 p-3 space-y-2 bg-[#F5F5F7]">
          {!loading && pending.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-2xl bg-white border border-black/5 flex items-center justify-center">
                <Inbox size={20} className="text-neutral-400" aria-hidden />
              </div>
              <p className="mt-4 text-sm font-semibold text-neutral-900">
                Nothing needs you right now.
              </p>
              <p className="mt-1 text-xs text-neutral-400 leading-relaxed max-w-[16rem]">
                NOCTRA is still watching. Cases appear here the moment they need a human decision.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {pending.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => goCase(c.id)}
                    className="w-full text-left rounded-2xl border border-black/5 bg-white p-4 shadow-card hover:shadow-float hover:-translate-y-px transition group cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <SeverityBadge severity={c.priority} />
                      <span className="ml-auto text-[10px] font-mono text-neutral-400 shrink-0">
                        {timeAgo(c.created_at)}
                      </span>
                    </span>
                    <span className="mt-2 block text-sm font-semibold text-neutral-900 leading-snug group-hover:text-violet-600 transition">
                      {c.title}
                    </span>
                    {c.proposed_action && (
                      <span className="mt-1.5 block text-[11px] font-mono text-violet-600">
                        {c.proposed_action.action_type} → {c.proposed_action.target}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer — the "checkout" CTA */}
        <div className="p-4 border-t border-black/5 shrink-0 bg-white">
          <button
            type="button"
            onClick={() => {
              close();
              navigate("/feed");
            }}
            className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 rounded-full bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition shadow-float cursor-pointer"
          >
            Review & decide <ArrowRight size={15} aria-hidden />
          </button>
          <p className="mt-2.5 text-center text-[11px] text-neutral-400">
            Approving records an action — it never executes it.
          </p>
        </div>
      </aside>
    </>
  );
};

export default PendingDecisionsDrawer;
