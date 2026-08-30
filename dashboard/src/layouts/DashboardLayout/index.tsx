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
  ChevronsLeft,
  Rows3,
  ClipboardList,
  UploadCloud,
  Layers,
  Fingerprint,
  Cloud,
  Package,
  EyeOff,
  FileSearch,
  Share2 as Share2Icon,
  FileCheck,
  Shield,
  Bug,
  Search,
  Bot,
  Network,
  Boxes,
  Radar,
  ShieldQuestion,
  Timer,
  Archive,
  Gavel,
  Database,
  Radio,
  Store,
  Brain,
  ShieldAlert,
  Swords,
  FileDown,
  CheckCheck,
  BookOpen,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { cn } from "../../components/ui";
import BrandLogo from "../../components/BrandLogo";
import PageTransition from "../../components/PageTransition";
import CommandMenu from "../../components/CommandMenu";
import PendingDecisionsDrawer from "../../components/storefront/PendingDecisionsDrawer";

interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  badge?: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
  adminOnly?: boolean;
  collapsedByDefault?: boolean;
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Work",
    items: [
      { name: "Analyst Inbox", path: "/", icon: Home },
      { name: "Cases", path: "/feed", icon: Inbox },
      { name: "Alerts", path: "/alerts", icon: TriangleAlert },
      { name: "Incidents", path: "/incidents", icon: ClipboardList },
      { name: "Actions", path: "/actions", icon: ShieldCheck },
    ],
  },
  {
    label: "Understand",
    items: [
      { name: "SOC Cockpit", path: "/dashboard", icon: LayoutDashboard },
      { name: "Analytics", path: "/analytics", icon: BarChart3 },
      { name: "Entities & Graph", path: "/entities", icon: Share2 },
      { name: "Reports", path: "/reports", icon: ScrollText },
      { name: "Executive Risk", path: "/exec-risk", icon: Gavel },
    ],
  },
  {
    label: "Investigate",
    items: [
      { name: "Threat Hunting", path: "/hunting", icon: Search },
      { name: "Threat Intel", path: "/threat-intel", icon: Share2Icon },
      { name: "Forensics", path: "/forensics", icon: FileSearch },
      { name: "Identity Threats", path: "/itdr", icon: Fingerprint },
      { name: "ATT&CK Navigator", path: "/attack-navigator", icon: Network },
      { name: "Log Uploads", path: "/logs", icon: UploadCloud },
    ],
  },
  {
    label: "Respond",
    items: [
      { name: "Playbooks", path: "/soar", icon: Workflow },
      { name: "AI Agent", path: "/ai-agent", icon: Bot },
      { name: "Agent Chat", path: "/agent-chat", icon: Bot },
      { name: "Deception", path: "/deception", icon: EyeOff },
    ],
  },
  {
    label: "Reduce risk",
    items: [
      { name: "Security Operations", path: "/final10", icon: ShieldAlert },
      { name: "Vulnerabilities", path: "/vulns", icon: Bug },
      { name: "Cloud Posture", path: "/cspm", icon: Cloud },
      { name: "Software Supply Chain", path: "/sbom", icon: Package },
      { name: "Zero Trust Access", path: "/ztna", icon: Shield },
      { name: "Compliance", path: "/compliance", icon: FileCheck },
    ],
  },
  {
    label: "Operate",
    collapsedByDefault: true,
    items: [
      { name: "Approvals", path: "/approvals", icon: ShieldCheck },
      { name: "Response Times", path: "/response-times", icon: Timer },
      { name: "Detection Coverage", path: "/attack-coverage", icon: Radar },
      { name: "Asset Inventory", path: "/assets", icon: Boxes },
      { name: "Data Retention", path: "/retention", icon: Archive },
      { name: "Erasure Requests", path: "/erasure-requests", icon: ShieldQuestion },
      { name: "SOC TV Wall", path: "/soc-tv-wall", icon: Radio },
    ],
  },
  {
    label: "System",
    adminOnly: true,
    collapsedByDefault: true,
    items: [
      { name: "Admin Overview", path: "/admin", icon: ShieldCheck },
      { name: "Users", path: "/admin/users", icon: KeyRound },
      { name: "Tenants", path: "/admin/tenants", icon: Building2 },
      { name: "Roles", path: "/admin/roles", icon: ShieldCheck },
      { name: "Rules", path: "/admin/rules", icon: ListChecks },
      { name: "Reputation", path: "/admin/reputation", icon: Ban },
      { name: "Engine", path: "/admin/engine-settings", icon: Settings2 },
      { name: "Audit", path: "/admin/system-logs", icon: ScrollText },
      { name: "SSO & SCIM", path: "/admin/sso", icon: KeyRound },
      { name: "API Keys", path: "/admin/apikeys", icon: KeyRound },
      { name: "Compliance Packs", path: "/admin/compliance", icon: Boxes },
    ],
  },
];

type Density = "comfortable" | "compact";

export interface DashboardLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    NAV_SECTIONS.forEach(s => { if (s.collapsedByDefault) init[s.label] = true; });
    return init;
  });
  const [density, setDensity] = useState<Density>(() => {
    const saved = localStorage.getItem("td_density");
    return saved === "compact" ? "compact" : "comfortable";
  });
  const location = useLocation();

  useEffect(() => { setMobileNavOpen(false); }, [location.pathname]);

  useEffect(() => {
    const path = location.pathname;
    let title = "NOCTRA";
    const allItems = NAV_SECTIONS.flatMap(s => s.items);
    const match = allItems.find(i => path === i.path || (i.path !== "/" && path.startsWith(i.path)));
    if (match) title = match.name;
    else if (path === "/") title = "Analyst Inbox";
    else if (path.startsWith("/case/")) title = `Case #${path.split("/")[2] ?? ""}`;
    else if (path.startsWith("/profile") || path.startsWith("/account")) title = "Profile";
    document.title = `${title} — NOCTRA`;
  }, [location.pathname]);

  const username: string = localStorage.getItem("username") || "User";
  const userRole: string = (localStorage.getItem("user_role") || "user").toLowerCase();
  const isAdmin = userRole === "admin";
  const permissions: string[] = (() => {
    try { return JSON.parse(localStorage.getItem("user_permissions") || "[]"); } catch { return []; }
  })();
  const adminVisible = isAdmin || permissions.includes("audit:read") || permissions.includes("users:manage");

  const isActive = (item: NavItem): boolean =>
    item.path === "/" ? location.pathname === "/" : location.pathname === item.path || location.pathname.startsWith(item.path + "/") || (item.path !== "/" && location.pathname.startsWith(item.path) && item.path.length > 3);

  const toggleDensity = (): void => {
    const next: Density = density === "comfortable" ? "compact" : "comfortable";
    setDensity(next);
    localStorage.setItem("td_density", next);
  };

  const toggleSection = (label: string) => {
    setCollapsedSections(prev => ({ ...prev, [label]: !prev[label] }));
  };

  const renderItem = (item: NavItem): React.ReactElement => {
    const active = isActive(item);
    const Icon = item.icon;
    return (
      <Link
        key={item.name}
        to={item.path}
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 px-3.5 py-2 rounded-sm text-xs font-semibold transition border-l-2 group ${
          active ? "border-accent-primary bg-accent-primary/10 text-accent-primary" : "border-transparent text-content-secondary hover:bg-app-subtle hover:text-accent-primary"
        }`}
      >
        <Icon size={16} className="shrink-0" aria-hidden />
        {isSidebarOpen && (
          <>
            <span className="truncate flex-1">{item.name}</span>
            {item.badge && <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${active ? "bg-accent-primary text-black" : "bg-app-subtle text-content-tertiary group-hover:bg-accent-primary/20"}`}>{item.badge}</span>}
          </>
        )}
        {!isSidebarOpen && <span className="sr-only">{item.name}</span>}
      </Link>
    );
  };

  const sectionLabel = (label: string): string => (isSidebarOpen ? label : "·");

  return (
    <div className="noctra-canvas h-screen w-screen text-content-primary flex overflow-hidden font-sans" data-density={density}>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:px-3 focus:py-2 focus:rounded-lg focus:bg-app-surface focus:border focus:border-line-subtle focus:text-content-primary focus:text-sm focus:shadow-overlay">Skip to content</a>
      {mobileNavOpen && <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={() => setMobileNavOpen(false)} aria-hidden />}

      <aside className={cn("bg-app-surface border-r border-line-subtle transition-all duration-300 flex-col justify-between shrink-0 overflow-hidden", "fixed inset-y-0 left-0 z-40 lg:static", mobileNavOpen ? "flex w-64" : "hidden lg:flex", isSidebarOpen ? "lg:w-64" : "lg:w-[68px]")}>
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className={cn("h-16 flex items-center border-b border-line-subtle shrink-0 transition-all duration-300", mobileNavOpen || isSidebarOpen ? "justify-between px-4" : "justify-center px-2")}>
            <Link to="/" className="flex items-center min-w-0 hover:opacity-80 transition">
              <BrandLogo collapsed={!isSidebarOpen && !mobileNavOpen} size={isSidebarOpen || mobileNavOpen ? 28 : 22} />
            </Link>
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} aria-label={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"} className="group p-1.5 rounded-full bg-app-subtle hover:bg-app-surface-raised text-content-secondary hover:text-content-primary active:scale-90 transition-all duration-200 cursor-pointer shrink-0 border border-line-subtle" title={isSidebarOpen ? "Collapse navigation" : "Expand navigation"} type="button">
              <ChevronsLeft size={15} aria-hidden className={cn("transition-transform duration-300 ease-out", !isSidebarOpen && "rotate-180")} />
            </button>
          </div>

          <nav aria-label="Primary" className="p-3 space-y-3 mt-1 flex-1 overflow-y-auto min-h-0">
            <button type="button" onClick={() => setMobileNavOpen(false)} className="lg:hidden w-full flex items-center justify-end px-3.5 pb-1 text-content-tertiary hover:text-content-primary transition text-xs font-bold cursor-pointer">Close ×</button>
            {NAV_SECTIONS.map(section => {
              if (section.adminOnly && !adminVisible) return null;
              const collapsed = collapsedSections[section.label];
              return (
                <div key={section.label} className="space-y-1">
                  <button onClick={() => toggleSection(section.label)} className={cn("w-full flex items-center justify-between px-3.5 pb-1.5 tech-label text-content-tertiary hover:text-content-secondary transition", !isSidebarOpen && "justify-center")}>
                    <span>{sectionLabel(section.label)}</span>
                    {isSidebarOpen && <span className="text-[10px]">{collapsed ? "▶" : "▼"}</span>}
                  </button>
                  {!collapsed && <div className="space-y-0.5">{section.items.map(renderItem)}</div>}
                </div>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-line-subtle flex items-center gap-3 shrink-0 bg-app-subtle/50">
          <div className="w-9 h-9 rounded-full bg-brand-gradient text-brand-ink flex items-center justify-center font-bold text-sm shrink-0">{username.charAt(0).toUpperCase()}</div>
          {isSidebarOpen && <div className="overflow-hidden flex-1 min-w-0"><p className="text-xs font-bold text-content-primary truncate">{username}</p><p className="text-[10px] font-medium text-accent-secondary capitalize">{userRole}</p></div>}
          <button type="button" onClick={toggleDensity} title={density === "comfortable" ? "Switch to compact" : "Switch to comfortable"} aria-pressed={density === "compact"} className="p-1.5 rounded-full text-content-tertiary hover:bg-app-subtle hover:text-content-secondary transition cursor-pointer"><Rows3 size={15} aria-hidden /></button>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
        <Navbar onLogout={onLogout} onOpenNav={() => setMobileNavOpen(true)} />
        <CommandMenu />
        <PendingDecisionsDrawer />
        <main key={location.pathname} id="main-content" tabIndex={-1} className="p-6 flex-1 min-w-0 w-full overflow-y-auto focus:outline-none bg-app-bg">
          <PageTransition>{children || <Outlet />}</PageTransition>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
