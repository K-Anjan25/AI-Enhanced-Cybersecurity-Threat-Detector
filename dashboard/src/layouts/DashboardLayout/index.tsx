import React, { ReactNode, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import Navbar from "../../components/Navbar";
import {
  TriangleAlert,
  Workflow,
  Share2,
  ScrollText,
  ShieldCheck,
  LayoutDashboard,
  Home,
  Inbox,
  Building2,
  KeyRound,
  ListChecks,
  Ban,
  BarChart3,
  Settings2,
  Rows3,
  ClipboardList,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../../components/ui";
import BrandLogo from "../../components/BrandLogo";
import PageTransition from "../../components/PageTransition";
import CommandMenu from "../../components/CommandMenu";
import PendingDecisionsDrawer from "../../components/storefront/PendingDecisionsDrawer";

/**
 * NOCTRA navigation (spec §8). Four MAIN items mirror the analyst loop —
 * SENSE (Home) → REASON (Cases) → DECIDE (Actions) → REPORT (Reports).
 * Everything else is grouped by verb and progressive-disclosed, never removed:
 * INVESTIGATE keeps the legacy deep-dive surfaces at their original URLs.
 */
interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  matchPrefix?: boolean;
}

const MAIN_NAV_ITEMS: NavItem[] = [
  { name: "Home", path: "/", icon: Home },
  { name: "Cases", path: "/feed", icon: Inbox },
  { name: "Actions", path: "/actions", icon: ShieldCheck },
  { name: "Reports", path: "/reports", icon: ScrollText },
];

const INVESTIGATE_NAV_ITEMS: NavItem[] = [
  { name: "Alerts", path: "/alerts", icon: TriangleAlert },
  { name: "Entities & Graph", path: "/entities", icon: Share2 },
  { name: "Analytics", path: "/analytics", icon: BarChart3 },
  { name: "SOC Cockpit", path: "/dashboard", icon: LayoutDashboard },
  { name: "Manual Incidents", path: "/incidents", icon: ClipboardList },
  { name: "Log Uploads", path: "/logs", icon: UploadCloud },
];

const AUTOMATE_NAV_ITEMS: NavItem[] = [
  { name: "SOAR", path: "/soar", icon: Workflow },
  { name: "Rules", path: "/admin/rules", icon: ListChecks },
];

const SYSTEM_NAV_ITEMS: NavItem[] = [
  { name: "Audit", path: "/admin/system-logs", icon: ScrollText },
  { name: "Reputation", path: "/admin/reputation", icon: Ban },
  { name: "Engine", path: "/admin/engine-settings", icon: Settings2 },
  // Admin Overview kept so /admin stays reachable from the nav (no route
  // loses its entry — see spec §7 progressive disclosure).
  { name: "Admin Overview", path: "/admin", icon: ShieldCheck },
  { name: "Users", path: "/admin/users", icon: KeyRound },
  { name: "Tenants", path: "/admin/tenants", icon: Building2 },
  { name: "Roles", path: "/admin/roles", icon: ShieldCheck },
];

type Density = "comfortable" | "compact";

export interface DashboardLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false);
  const [density, setDensity] = useState<Density>(() => {
    const saved = localStorage.getItem("td_density");
    return saved === "compact" ? "compact" : "comfortable";
  });
  const location = useLocation();

  // Route changes always close the mobile drawer.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Per-route document titles (tab + screen-reader context).
  useEffect(() => {
    const path = location.pathname;
    let title = "NOCTRA";
    if (path === "/") title = "Analyst Inbox";
    else if (path.startsWith("/case/")) title = `Case #${path.split("/")[2] ?? ""}`;
    else if (path.startsWith("/feed")) title = "Cases";
    else if (path.startsWith("/actions")) title = "Actions";
    else if (path.startsWith("/reports")) title = "Reports";
    else if (path.startsWith("/alerts")) title = "Alerts";
    else if (path.startsWith("/entities")) title = "Entities & Graph";
    else if (path.startsWith("/analytics")) title = "Analytics";
    else if (path.startsWith("/dashboard")) title = "SOC Cockpit";
    else if (path.startsWith("/soar")) title = "SOAR";
    else if (path.startsWith("/incidents")) title = "Manual Incidents";
    else if (path.startsWith("/logs")) title = "Log Uploads";
    else if (path.startsWith("/profile") || path.startsWith("/account")) title = "Profile";
    else if (path.startsWith("/admin")) title = "Administration";
    document.title = `${title} — NOCTRA`;
  }, [location.pathname]);

  const username: string = localStorage.getItem("username") || "User";
  const userRole: string = (localStorage.getItem("user_role") || "user").toLowerCase();
  const isAdmin = userRole === "admin";
  const { permissions } = {
    permissions: (() => {
      try {
        return JSON.parse(localStorage.getItem("user_permissions") || "[]");
      } catch {
        return [];
      }
    })(),
  };
  const adminVisible = isAdmin || permissions.includes("audit:read") || permissions.includes("users:manage");

  const isActive = (item: NavItem): boolean =>
    item.path === "/"
      ? location.pathname === "/"
      : item.matchPrefix
      ? location.pathname.startsWith(item.path)
      : location.pathname === item.path;

  const toggleDensity = (): void => {
    const next: Density = density === "comfortable" ? "compact" : "comfortable";
    setDensity(next);
    localStorage.setItem("td_density", next);
  };

  const renderItem = (item: NavItem): React.ReactElement => {
    const active = isActive(item);
    const Icon = item.icon;
    return (
      <Link
        key={item.name}
        to={item.path}
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-full text-xs font-semibold transition ${
          active
            ? "bg-brand-gradient text-brand-ink shadow-float"
            : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900"
        }`}
      >
        <Icon size={17} className="shrink-0" aria-hidden />
        {isSidebarOpen && <span className="truncate">{item.name}</span>}
        {!isSidebarOpen && <span className="sr-only">{item.name}</span>}
      </Link>
    );
  };

  const sectionLabel = (label: string): string => (isSidebarOpen ? label : "·");

  return (
    <div
      className="h-screen w-screen bg-app-bg text-content-primary flex overflow-hidden font-sans"
      data-density={density}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:px-3 focus:py-2 focus:rounded-lg focus:bg-app-surface focus:border focus:border-line-subtle focus:text-content-primary focus:text-sm focus:shadow-overlay"
      >
        Skip to content
      </a>

      {/* Mobile drawer backdrop */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          "bg-white border-r border-black/5 transition-all duration-300 flex-col justify-between shrink-0 overflow-hidden",
          // Mobile: overlay drawer (open only). Desktop: static column.
          "fixed inset-y-0 left-0 z-40 lg:static",
          mobileNavOpen ? "flex w-64" : "hidden lg:flex",
          isSidebarOpen ? "lg:w-64" : "lg:w-[68px]"
        )}
      >
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="h-16 flex items-center justify-between px-4 border-b border-black/5 shrink-0">
            <Link to="/" className="flex items-center min-w-0 hover:opacity-80 transition">
              <BrandLogo collapsed={!isSidebarOpen} size={isSidebarOpen ? 28 : 26} />
            </Link>
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={cn(
                "p-1.5 rounded-full bg-neutral-100 hover:bg-neutral-200 text-neutral-500 hover:text-neutral-900 transition text-xs font-bold cursor-pointer shrink-0 border border-black/5",
                isSidebarOpen ? "" : "mx-auto"
              )}
              title={isSidebarOpen ? "Collapse navigation" : "Expand navigation"}
              type="button"
            >
              {isSidebarOpen ? "«" : "»"}
            </button>
          </div>

          <nav aria-label="Primary" className="p-3 space-y-1 mt-2 flex-1 overflow-y-auto min-h-0">
            {/* Mobile-only close inside the drawer */}
            <button
              type="button"
              onClick={() => setMobileNavOpen(false)}
              className="lg:hidden w-full flex items-center justify-end px-3.5 pb-1 text-neutral-400 hover:text-neutral-900 transition text-xs font-bold cursor-pointer"
            >
              Close ×
            </button>
            <p
              className={cn(
                "px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-neutral-400",
                !isSidebarOpen && "text-center"
              )}
            >
              {sectionLabel("Main")}
            </p>
            {MAIN_NAV_ITEMS.map(renderItem)}

            <div className="pt-3 mt-3 border-t border-black/5 space-y-1">
              <p className={cn("px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-neutral-400", !isSidebarOpen && "text-center")}>
                {sectionLabel("Investigate")}
              </p>
              {INVESTIGATE_NAV_ITEMS.map(renderItem)}
            </div>

            <div className="pt-3 mt-3 border-t border-black/5 space-y-1">
              <p className={cn("px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-neutral-400", !isSidebarOpen && "text-center")}>
                {sectionLabel("Automate")}
              </p>
              {adminVisible ? (
                AUTOMATE_NAV_ITEMS.map(renderItem)
              ) : (
                renderItem(AUTOMATE_NAV_ITEMS[0])
              )}
            </div>

            {adminVisible && (
              <div className="pt-3 mt-3 border-t border-black/5 space-y-1">
                <p className={cn("px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-neutral-400", !isSidebarOpen && "text-center")}>
                  {sectionLabel("System")}
                </p>
                {SYSTEM_NAV_ITEMS.map(renderItem)}
              </div>
            )}
          </nav>
        </div>

        <div className="p-4 border-t border-black/5 flex items-center gap-3 shrink-0 bg-neutral-50/50">
          <div className="w-9 h-9 rounded-full bg-brand-gradient text-brand-ink flex items-center justify-center font-bold text-sm shrink-0">
            {username.charAt(0).toUpperCase()}
          </div>
          {isSidebarOpen && (
            <div className="overflow-hidden flex-1 min-w-0">
              <p className="text-xs font-bold text-neutral-900 truncate">{username}</p>
              <p className="text-[10px] font-medium text-violet-600 capitalize">{userRole}</p>
            </div>
          )}
          <button
            type="button"
            onClick={toggleDensity}
            title={density === "comfortable" ? "Switch to compact density" : "Switch to comfortable density"}
            aria-pressed={density === "compact"}
            className="p-1.5 rounded-full text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 transition cursor-pointer"
          >
            <Rows3 size={15} aria-hidden />
          </button>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
        <Navbar onLogout={onLogout} onOpenNav={() => setMobileNavOpen(true)} />
        <CommandMenu />
        <PendingDecisionsDrawer />

        <main
          key={location.pathname}
          id="main-content"
          tabIndex={-1}
          className="p-6 flex-1 min-w-0 w-full overflow-y-auto focus:outline-none bg-[#F5F5F7]"
        >
          <PageTransition>{children || <Outlet />}</PageTransition>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
