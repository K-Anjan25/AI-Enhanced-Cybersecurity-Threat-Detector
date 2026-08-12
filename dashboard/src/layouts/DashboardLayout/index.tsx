import React, { ReactNode, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import Navbar from "../../components/Navbar";

export interface NavItem {
  name: string;
  path: string;
  icon: string;
}

export interface DashboardLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(true);
  const location = useLocation();

  const username: string = localStorage.getItem("username") || "User";

  // Simplified basic navigation items for testing
  const navItems: NavItem[] = [
    { name: "Dashboard", path: "/dashboard", icon: "DSH" },
    { name: "Threat Alerts", path: "/alerts", icon: "ALT" },
    { name: "Log History", path: "/logs", icon: "LOG" },
    { name: "Profile Settings", path: "/profile", icon: "SET" },
  ];

  return (
    <div className="h-screen w-screen bg-app-bg text-content-primary flex overflow-hidden">
      <aside
        className={`${
          isSidebarOpen ? "w-64" : "w-20"
        } bg-app-surface border-r border-line-subtle transition-all duration-300 flex flex-col justify-between shrink-0 z-30`}
      >
        <div>
          <div className="h-16 flex items-center justify-between px-4 border-b border-line-subtle">
            {isSidebarOpen && (
              <span className="text-lg font-bold text-accent-primary truncate tracking-tight">
                ThreatDetector AI
              </span>
            )}
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 rounded-lg bg-app-subtle hover:bg-line-bright text-content-secondary transition mx-auto text-xs font-semibold"
              title="Toggle Navigation"
              type="button"
            >
              Menu
            </button>
          </div>

          <nav className="p-3 space-y-1.5 mt-2">
            {navItems.map((item: NavItem) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.name}
                  to={item.path}
                  className={`flex items-center gap-3.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition ${
                    isActive
                      ? "bg-accent-primary/10 text-accent-primary border border-accent-primary/30"
                      : "text-content-secondary hover:bg-app-subtle hover:text-content-primary"
                  }`}
                >
                  <span className="text-xs font-bold w-8">{item.icon}</span>
                  {isSidebarOpen && <span>{item.name}</span>}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-line-subtle flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-accent-primary text-app-bg flex items-center justify-center font-bold shrink-0">
            {username.charAt(0).toUpperCase()}
          </div>
          {isSidebarOpen && (
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-content-primary truncate">{username}</p>
              <p className="text-xs text-accent-primary">Test Mode</p>
            </div>
          )}
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden">
        <Navbar onLogout={onLogout} />

        <main className="p-6 flex-1 min-w-0 w-full overflow-y-auto">
          {children || <Outlet />}
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;