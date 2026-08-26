"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/store/userStore";
import { 
  Menu, 
  LogOut, 
  User, 
  Shield, 
  Alert, 
  Folder, 
  PieChart, 
  Server, 
  Settings,
  FolderSearch,
  LayoutDashboard,
  Microscope
} from "lucide-react";

export function Sidebar() {
  const { user, orgId, switchOrg } = useAuth();
  const router = useRouter();

  const navItems = [
    { key: "overview", label: "Overview", icon: LayoutDashboard, href: "/dashboard" },
    { key: "alerts", label: "Alerts", icon: Alert, href: "/dashboard/alerts" },
    { key: "cases", label: "Incidents", icon: Folder, href: "/dashboard/cases" },
    { key: "soar", label: "SOAR", icon: Server, href: "/dashboard/soar" },
    { key: "entities", label: "Entities", icon: Microscope, href: "/dashboard/entities" },
    { key: "analytics", label: "Analytics", icon: PieChart, href: "/dashboard/analytics" },
    { key: "rules", label: "Rules", icon: FolderSearch, href: "/dashboard/rules" },
  ];

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <aside className="w-64 sm:w-auto bg-surface border-r border-divider flex-shrink-0">
      <div className="p-4 border-b border-divider">
        <a href="/dashboard" className="flex items-center gap-2 text-accent hover:text-foreground transition-colors">
          <svg
            className="h-6 w-6"
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <path d="M3 4h18v2H3V4zm0 7h12v2H3v-2zm0 7h18v2H3v-2z" />
          </svg>
          NOCTRA
        </a>
      </div>

      <nav className="flex flex-col pt-2 gap-1 px-2">
        {navItems.map((item) => {
          const isActive = item.key === getActiveSection();
          
          return (
            <button
              key={item.key}
              onClick={() => router.push(item.href)}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-foreground transition-colors ${isActive 
                ? "bg-accent text-white" 
                : "hover:bg-surface-muted hover:text-foreground"}`}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="sr-only">{item.label}</span>
              {item.label}
            </button>
          );
        })}

        <div className="mt-auto pt-4 border-t border-divider">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium text-muted"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </div>
      </nav>
    </aside>
  );
}

function getActiveSection(): string {
  const path = window.location.pathname;
  if (path.includes("/dashboard")) return "overview";
  if (path.includes("/alerts")) return "alerts";
  if (path.includes("/cases")) return "cases";
  if (path.includes("/soar")) return "soar";
  if (path.includes("/entities")) return "entities";
  if (path.includes("/analytics")) return "analytics";
  if (path.includes("/rules")) return "rules";
  return "overview";
}