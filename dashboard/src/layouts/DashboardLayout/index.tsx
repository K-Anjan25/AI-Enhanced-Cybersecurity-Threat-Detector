import React, { ReactNode, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import Navbar from "../../components/Navbar";
import {
  TriangleAlert,
  FolderKanban,
  Workflow,
  Share2,
  ScrollText,
  ShieldCheck,
  LayoutDashboard,
  Sparkles,
  Inbox,
  Building2,
  KeyRound,
  ListChecks,
  Ban,
  Rows3,
  Settings,
  ChevronDown,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../../components/ui";
import BrandLogo from "../../components/BrandLogo";
import PageTransition from "../../components/PageTransition";

interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  admin?: boolean;
  matchPrefix?: boolean;
}

const PRIMARY_NAV_ITEMS: NavItem[] = [
  { name: "Inbox & Brief", path: "/", icon: Sparkles },
  { name: "Cases Queue", path: "/feed", icon: Inbox },
  { name: "Actions Log", path: "/actions", icon: ShieldCheck },
  { name: "Incident Reports", path: "/reports", icon: ScrollText },
];

const ADVANCED_NAV_ITEMS: NavItem[] = [
  { name: "Threat Graph", path: "/entities", icon: Share2 },
  { name: "Alert Telemetry", path: "/alerts", icon: TriangleAlert },
  { name: "SOAR Automation", path: "/soar", icon: Workflow },
  { name: "SOC Cockpit", path: "/dashboard", icon: LayoutDashboard },
];

const ADMIN_ITEMS: NavItem[] = [
  { name: "Admin Overview", path: "/admin", icon: Settings, matchPrefix: true },
  { name: "User Management", path: "/admin/users", icon: KeyRound },
  { name: "Tenants", path: "/admin/tenants", icon: Building2 },
  { name: "Detection Rules", path: "/admin/rules", icon: ListChecks },
  { name: "IP Reputation", path: "/admin/reputation", icon: Ban },
  { name: "System Audit Logs", path: "/admin/system-logs", icon: ScrollText },
];

type Density = "comfortable" | "compact";

export interface DashboardLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [showAdvanced, setShowAdvanced] = useState<boolean>(true);
  const [density, setDensity] = useState<Density>(() => {
    const saved = localStorage.getItem("td_density");
    return saved === "compact" ? "compact" : "comfortable";
  });
  const location = useLocation();

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
        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition ${
          active
            ? "bg-blue-50 text-blue-600 border border-blue-200 shadow-sm"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 border border-transparent"
        }`}
      >
        <Icon size={17} className="shrink-0" aria-hidden />
        {isSidebarOpen && <span className="truncate">{item.name}</span>}
        {!isSidebarOpen && <span className="sr-only">{item.name}</span>}
      </Link>
    );
  };

  return (
    <div
      className="h-screen w-screen bg-app-bg text-content-primary flex overflow-hidden font-sans"
      data-density={density}
    >
      <aside
        className={cn(
          "bg-white border-r border-line-subtle transition-all duration-300 flex flex-col justify-between shrink-0 z-30 overflow-hidden shadow-card",
          isSidebarOpen ? "w-64" : "w-[68px]"
        )}
      >
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="h-16 flex items-center justify-between px-4 border-b border-line-subtle shrink-0">
            <Link to="/" className="flex items-center min-w-0 hover:opacity-90 transition">
              <BrandLogo collapsed={!isSidebarOpen} size={isSidebarOpen ? 28 : 26} />
            </Link>
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={cn(
                "p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 transition text-xs font-bold cursor-pointer shrink-0 border border-slate-200",
                isSidebarOpen ? "" : "mx-auto"
              )}
              title={isSidebarOpen ? "Collapse navigation" : "Expand navigation"}
              type="button"
            >
              {isSidebarOpen ? "«" : "»"}
            </button>
          </div>

          <nav className="p-3 space-y-1 mt-2 flex-1 overflow-y-auto min-h-0">
            <p className={cn("px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400", !isSidebarOpen && "text-center")}>
              {isSidebarOpen ? "Analyst Workspace" : "·"}
            </p>
            {PRIMARY_NAV_ITEMS.map(renderItem)}

            {/* Advanced / Deep-Dive Accordion */}
            <div className="pt-3 mt-3 border-t border-slate-100 space-y-1">
              {isSidebarOpen ? (
                <button
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="w-full flex items-center justify-between px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <span>Advanced Tools</span>
                  {showAdvanced ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                </button>
              ) : (
                <p className="text-center text-[10px] font-bold uppercase text-slate-400 pb-1">·</p>
              )}
              {(showAdvanced || !isSidebarOpen) && ADVANCED_NAV_ITEMS.map(renderItem)}
            </div>

            {adminVisible && (
              <div className="pt-3 mt-3 border-t border-slate-100 space-y-1">
                <p className={cn("px-3.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400", !isSidebarOpen && "text-center")}>
                  {isSidebarOpen ? "Administration" : "·"}
                </p>
                {ADMIN_ITEMS.map(renderItem)}
              </div>
            )}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-100 flex items-center gap-3 shrink-0 bg-slate-50/50">
          <div className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-sm shrink-0 shadow-sm">
            {username.charAt(0).toUpperCase()}
          </div>
          {isSidebarOpen && (
            <div className="overflow-hidden flex-1 min-w-0">
              <p className="text-xs font-bold text-slate-900 truncate">{username}</p>
              <p className="text-[10px] font-medium text-blue-600 capitalize">{userRole}</p>
            </div>
          )}
          <button
            type="button"
            onClick={toggleDensity}
            title={density === "comfortable" ? "Switch to compact density" : "Switch to comfortable density"}
            aria-pressed={density === "compact"}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition cursor-pointer"
          >
            <Rows3 size={15} aria-hidden />
          </button>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
        <Navbar onLogout={onLogout} />

        <main key={location.pathname} className="p-6 flex-1 min-w-0 w-full overflow-y-auto">
          <PageTransition>{children || <Outlet />}</PageTransition>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
