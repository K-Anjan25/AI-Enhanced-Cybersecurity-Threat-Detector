import React, { ReactNode, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import Navbar from "../../components/Navbar";
import {
  TriangleAlert,
  FolderKanban,
  Workflow,
  Share2,
  ScrollText,
  ChartColumn,
  Settings,
  ShieldCheck,
  LayoutDashboard,
  Building2,
  KeyRound,
  ListChecks,
  Ban,
  Rows3,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../../components/ui";
import BrandLogo from "../../components/BrandLogo";

interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  admin?: boolean;
  matchPrefix?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { name: "Overview", path: "/", icon: LayoutDashboard },
  { name: "Threat Alerts", path: "/alerts", icon: TriangleAlert },
  { name: "Incidents", path: "/incidents", icon: FolderKanban },
  { name: "Entity Graph", path: "/entities", icon: Share2 },
  { name: "SOAR Automation", path: "/soar", icon: Workflow },
  { name: "AI Analytics", path: "/analytics", icon: ChartColumn },
  { name: "Log History", path: "/logs", icon: ScrollText },
];

const ADMIN_ITEMS: NavItem[] = [
  { name: "Admin Console", path: "/admin", icon: ShieldCheck, matchPrefix: true },
  { name: "User Management", path: "/admin/users", icon: Settings },
  { name: "Tenants", path: "/admin/tenants", icon: Building2 },
  { name: "Access Roles", path: "/admin/roles", icon: KeyRound },
  { name: "Detection Rules", path: "/admin/rules", icon: ListChecks },
  { name: "IP Reputation", path: "/admin/reputation", icon: Ban },
];

type Density = "comfortable" | "compact";

export interface DashboardLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
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
      ? location.pathname === "/" || location.pathname === "/dashboard"
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
        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition ${
          active
            ? "bg-accent-primary/10 text-accent-primary border border-accent-primary/30"
            : "text-content-secondary hover:bg-app-subtle hover:text-content-primary border border-transparent"
        }`}
      >
        <Icon size={18} className="shrink-0" aria-hidden />
        {isSidebarOpen && <span className="truncate">{item.name}</span>}
        {!isSidebarOpen && <span className="sr-only">{item.name}</span>}
      </Link>
    );
  };

  return (
    <div
      className="h-screen w-screen bg-app-bg text-content-primary flex overflow-hidden"
      data-density={density}
    >
      <aside
        className={cn(
          "bg-app-surface border-r border-line-subtle transition-all duration-300 flex flex-col justify-between shrink-0 z-30 overflow-hidden",
          isSidebarOpen ? "w-64" : "w-[68px]"
        )}
      >
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="h-16 flex items-center justify-between px-3 border-b border-line-subtle shrink-0">
            <Link to="/" className="flex items-center min-w-0 hover:opacity-90 transition">
              <BrandLogo collapsed={!isSidebarOpen} size={isSidebarOpen ? 28 : 26} />
            </Link>
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className={cn(
                "p-2 rounded-lg bg-app-subtle hover:bg-line-bright text-content-secondary transition text-xs font-semibold cursor-pointer shrink-0",
                isSidebarOpen ? "" : "mx-auto"
              )}
              title={isSidebarOpen ? "Collapse navigation" : "Expand navigation"}
              type="button"
            >
              {isSidebarOpen ? "«" : "»"}
            </button>
          </div>

          {/* Scrollable nav: overflow-y-auto keeps the footer pinned when the
              item list exceeds the viewport height. */}
          <nav className="p-3 space-y-1.5 mt-2 flex-1 overflow-y-auto min-h-0">
            {NAV_ITEMS.map(renderItem)}

            {adminVisible && (
              <div className="pt-3 mt-3 border-t border-line-subtle space-y-1.5">
                <p className={cn("px-3.5 pb-1 text-xs font-bold uppercase tracking-wider text-content-tertiary", !isSidebarOpen && "text-center")}>
                  {isSidebarOpen ? "Administration" : "·"}
                </p>
                {ADMIN_ITEMS.map(renderItem)}
              </div>
            )}
          </nav>
        </div>

        <div className="p-4 border-t border-line-subtle flex items-center gap-3 shrink-0">
          <div className="w-9 h-9 rounded-full bg-accent-primary text-app-bg flex items-center justify-center font-bold shrink-0">
            {username.charAt(0).toUpperCase()}
          </div>
          {isSidebarOpen && (
            <div className="overflow-hidden flex-1 min-w-0">
              <p className="text-sm font-semibold text-content-primary truncate">{username}</p>
              <p className="text-xs text-accent-primary capitalize">{userRole}</p>
            </div>
          )}
          <button
            type="button"
            onClick={toggleDensity}
            title={density === "comfortable" ? "Switch to compact density" : "Switch to comfortable density"}
            aria-pressed={density === "compact"}
            className="p-2 rounded-lg text-content-secondary hover:bg-app-subtle hover:text-content-primary transition cursor-pointer"
          >
            <Rows3 size={16} aria-hidden />
          </button>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
        <Navbar onLogout={onLogout} />

        <main key={location.pathname} className="p-6 flex-1 min-w-0 w-full overflow-y-auto animate-fade-up">
          {children || <Outlet />}
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;