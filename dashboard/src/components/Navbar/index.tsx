import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { logout } from "../../store/userActions";
import { Search, Settings, LogOut, ShieldCheck, Bell, Menu, Inbox, ArrowRight } from "lucide-react";
import BrandLogo from "../BrandLogo";
import { BRAND_TAGLINE } from "../../constants/brand";
import AnalystApi from "../../api/analystApi";
import type { NotificationItem } from "../../types/analyst";
import { EVENTS, emit } from "../../lib/events";
import { useNoctraEvent } from "../../hooks";
import ThemeToggle from "../ThemeToggle";

const SEEN_KEY = "noctra_notified_at";

export interface NavbarProps {
  onLogout?: () => void;
  /** Opens the mobile navigation drawer (rendered by DashboardLayout). */
  onOpenNav?: () => void;
}

const Navbar: React.FC<NavbarProps> = ({ onLogout, onOpenNav }) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState<boolean>(false);
  const [isNotesOpen, setIsNotesOpen] = useState<boolean>(false);
  const [notes, setNotes] = useState<NotificationItem[]>([]);
  const [seenAt, setSeenAt] = useState<string>(() => localStorage.getItem(SEEN_KEY) ?? "");
  const [search, setSearch] = useState<string>("");
  const [pendingCount, setPendingCount] = useState<number>(0);
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const headerRef = useRef<HTMLElement>(null);

  // Live pending count — the mini-cart pattern: the "Review decisions"
  // button carries a count pill that updates whenever a case is decided
  // (case page, drawer, anywhere) via the event bus.
  useNoctraEvent(EVENTS.PENDING_CHANGED, (n) => setPendingCount(Number(n) || 0));

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!headerRef.current?.contains(e.target as Node)) {
        setIsNotesOpen(false);
        setIsProfileMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsNotesOpen(false);
        setIsProfileMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const username: string = localStorage.getItem("username") || "User";
  const userRole: string = (localStorage.getItem("user_role") || "user").toLowerCase();

  const loadNotes = useCallback(() => {
    AnalystApi.fetchNotifications()
      .then((res) => setNotes(res.items ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadNotes();
    const interval = setInterval(loadNotes, 60000);
    return () => clearInterval(interval);
  }, [loadNotes]);

  const unreadCount = notes.filter((n) => !seenAt || n.at > seenAt).length;

  useEffect(() => {
    const pending = notes.filter((n) => n.kind === "decision_pending").length;
    if (pending > 0) setPendingCount(pending);
  }, [notes]);

  const openNotes = () => {
    setIsNotesOpen((v) => !v);
    setIsProfileMenuOpen(false);
    const now = new Date().toISOString();
    localStorage.setItem(SEEN_KEY, now);
    setSeenAt(now);
  };

  const handleLogout = (): void => {
    setIsProfileMenuOpen(false);
    dispatch(logout() as any);
    onLogout?.();
    navigate("/login");
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter" && search.trim()) {
      navigate(`/alerts?q=${encodeURIComponent(search.trim())}`);
      setSearch("");
    }
  };

  return (
    <header
      ref={headerRef}
      className="h-16 bg-app-surface/80 backdrop-blur-xl border-b border-line-subtle flex items-center justify-between px-3 sm:px-6 shrink-0 z-20 w-full gap-2 sticky top-0"
    >
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onOpenNav}
          aria-label="Open navigation"
          className="lg:hidden w-9 h-9 rounded-full bg-app-subtle border border-line-subtle text-content-secondary hover:text-content-primary transition flex items-center justify-center cursor-pointer shrink-0"
        >
          <Menu size={16} aria-hidden />
        </button>

        <Link to="/" className="flex items-center hover:opacity-80 transition min-w-0" aria-label="NOCTRA home">
          <span className="hidden lg:inline-flex">
            <BrandLogo size={26} />
          </span>
          <span className="lg:hidden inline-flex">
            <BrandLogo size={26} withWordmark={false} />
          </span>
        </Link>

        <span className="hidden xl:inline text-[11px] font-mono text-content-tertiary truncate">
          {BRAND_TAGLINE}
        </span>
      </div>

      <div className="w-80 max-w-[40%] hidden md:block">
        <div className="relative">
          <Search size={14} className="absolute inset-y-0 left-3.5 my-auto text-content-tertiary" aria-hidden />
          <input
            type="text"
            placeholder="Search IP, threat, hash…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="w-full bg-app-subtle/80 text-sm text-content-primary pl-9 pr-14 py-2 rounded-full border border-transparent focus:outline-none focus:border-accent-primary/40 focus:bg-app-surface transition placeholder-content-tertiary"
          />
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("noctra:command-menu"))}
            aria-label="Open command menu"
            title="Command menu (⌘K)"
            className="absolute inset-y-0 right-1.5 my-auto h-6 px-1.5 rounded-full border border-line-subtle bg-app-surface text-[10px] font-mono text-content-tertiary hover:text-content-primary transition cursor-pointer"
          >
            ⌘K
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={() => window.dispatchEvent(new Event("noctra:command-menu"))}
        aria-label="Open command menu"
        title="Command menu (⌘K)"
        className="md:hidden w-9 h-9 rounded-full bg-app-subtle border border-line-subtle text-content-secondary hover:text-content-primary transition flex items-center justify-center cursor-pointer"
      >
        <Search size={15} aria-hidden />
      </button>

      <div className="flex items-center gap-2">
        <ThemeToggle />

        {/* Mini-cart pattern: "Review decisions" with a live pending count pill. */}
        <button
          type="button"
          onClick={() => emit(EVENTS.OPEN_PENDING_DRAWER)}
          aria-label={`Review pending decisions${pendingCount ? ` — ${pendingCount} pending` : ""}`}
          className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-gradient text-brand-ink text-xs font-semibold hover:opacity-90 transition shadow-float cursor-pointer shrink-0"
        >
          Review decisions
          <span className="inline-flex items-center gap-1">
            {pendingCount > 0 && (
              <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-brand-ink/20 text-brand-ink text-[10px] font-bold flex items-center justify-center tabular-nums">
                {pendingCount > 99 ? "99+" : pendingCount}
              </span>
            )}
            <ArrowRight size={13} aria-hidden />
          </span>
        </button>

        <button
          type="button"
          onClick={() => emit(EVENTS.OPEN_PENDING_DRAWER)}
          aria-label={`Review pending decisions${pendingCount ? ` — ${pendingCount} pending` : ""}`}
          className="sm:hidden relative w-9 h-9 rounded-full bg-app-subtle border border-line-subtle text-content-secondary hover:text-content-primary transition flex items-center justify-center cursor-pointer shrink-0"
        >
          <Inbox size={16} aria-hidden />
          {pendingCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-status-critical text-white text-[9px] font-bold flex items-center justify-center tabular-nums">
              {pendingCount > 9 ? "9+" : pendingCount}
            </span>
          )}
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={openNotes}
            aria-label={`Notifications${unreadCount ? ` — ${unreadCount} unread` : ""}`}
            aria-haspopup="menu"
            aria-expanded={isNotesOpen}
            title="Notifications"
            className="relative w-9 h-9 rounded-full bg-app-subtle border border-line-subtle text-content-secondary hover:text-content-primary transition flex items-center justify-center cursor-pointer"
          >
            <Bell size={16} aria-hidden />
            {unreadCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-status-critical text-white text-[9px] font-bold flex items-center justify-center">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {isNotesOpen && (
            <div
              role="menu"
              aria-label="Notifications"
              className="absolute right-0 mt-2 w-80 bg-app-surface border border-line-subtle rounded-2xl shadow-overlay py-2 z-50 animate-scale-in"
            >
              <p className="px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-content-tertiary">
                Notifications
              </p>
              {notes.length === 0 ? (
                <p className="px-4 py-4 text-xs text-content-secondary">
                  Nothing needs your attention — no pending decisions, no recent outcomes.
                </p>
              ) : (
                <ul className="max-h-80 overflow-y-auto">
                  {notes.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setIsNotesOpen(false);
                          navigate(`/case/${n.case_id}`);
                        }}
                        className="w-full text-left px-4 py-2.5 hover:bg-app-subtle transition cursor-pointer"
                      >
                        <span className="flex items-center gap-2">
                          <span
                            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                              n.kind === "decision_pending" ? "bg-status-warning" : "bg-status-success"
                            }`}
                            aria-hidden
                          />
                          <span className="text-xs font-medium text-content-primary truncate">
                            {n.title}
                          </span>
                          <span className="ml-auto text-[10px] font-mono text-content-tertiary shrink-0">
                            {new Date(n.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </span>
                        <span className="block text-[11px] text-content-secondary mt-0.5 pl-3.5">
                          {n.detail} · case #{n.case_id}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setIsProfileMenuOpen(!isProfileMenuOpen);
              setIsNotesOpen(false);
            }}
            aria-expanded={isProfileMenuOpen}
            aria-haspopup="menu"
            className="w-9 h-9 rounded-full bg-brand-gradient text-brand-ink font-bold flex items-center justify-center hover:opacity-90 transition ring-2 ring-accent-primary/20 cursor-pointer"
          >
            {username.charAt(0).toUpperCase()}
          </button>

          {isProfileMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-56 bg-app-surface border border-line-subtle rounded-2xl shadow-overlay py-2 z-50 animate-scale-in"
            >
              <div className="px-4 py-2.5 border-b border-line-subtle flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-brand-gradient text-brand-ink flex items-center justify-center font-bold text-xs shrink-0">
                  {username.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-content-primary truncate">{username}</p>
                  <p className="text-xs text-accent-secondary capitalize flex items-center gap-1">
                    <ShieldCheck size={11} aria-hidden /> {userRole}
                  </p>
                </div>
              </div>

              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setIsProfileMenuOpen(false);
                  navigate("/profile");
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-content-secondary hover:bg-app-subtle hover:text-content-primary transition flex items-center gap-2.5 cursor-pointer"
              >
                <Settings size={15} aria-hidden /> Settings
              </button>

              <button
                type="button"
                role="menuitem"
                onClick={handleLogout}
                className="w-full text-left px-4 py-2.5 text-sm text-status-critical hover:bg-app-subtle transition flex items-center gap-2.5 cursor-pointer"
              >
                <LogOut size={15} aria-hidden /> Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Navbar;
