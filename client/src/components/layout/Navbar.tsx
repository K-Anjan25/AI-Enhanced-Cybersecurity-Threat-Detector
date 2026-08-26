"use client";

import { useState } from "react";
import { useSearchParams, useLocation } from "next/navigation";
import { useAuth } from "@/store/userStore";
import { 
  User, 
  LogOut, 
  Menu,
  ChevronDown,
  Shield,
  Mail,
  Search,
  Bell
} from "lucide-react";

export function Navbar() {
  const { user, logout } = useAuth();
  const searchParams = useSearchParams();
  const location = useLocation();

  const orgId = searchParams.get("org") || user.org_id;
  const [expanded, setExpanded] = useState(false);

  const handleLogout = async () => {
    await logout();
  };

  return (
    <header className="h-16 border-b border-divider bg-surface px-6 flex items-center justify-between shadow-sm">
      <div className="flex items-center gap-3">
        <a href="/dashboard" className="flex items-center gap-2">
          <svg
            className="h-7 w-7"
            viewBox="0 0 32 32"
            fill="none"
          >
            <circle cx="16" cy="16" r="14" fill="#0f0f0f" />
            <path d="M16 2 L28 10 V22 L16 30 L4 22 V10 Z" stroke="#3b82f6" stroke-width="1.6" fill="#0a0a0f"/>
            <path d="M11 16 C11 11.8 13.4 9.2 16 9.2 C18.6 9.2 21 11.8 21 16 C21 20.2 18.6 22.8 16 22.8 C13.4 22.8 11 20.2 11 16Z" stroke="#3b82f6" stroke-width="1.5" fill="none"/>
            <path d="M16 16 L16 9.2 A6.8 6.8 0 0 1 21 16 Z" fill="#3b82f6"/>
            <circle cx="16" cy="16" r="2.1" fill="#0a0a0f" stroke="#3b82f6" stroke-width="1.2"/>
          </svg>
          NOCTRA
        </a>
      </div>

      <div className="hidden sm:flex items-center gap-6">
        <Input
          placeholder="Search alerts..."
          className="flex-1 pr-4"
          value={searchParams.get("q") || ""}
          onChange={(e) => /* handle search */}
        />
        <Button variant="ghost" size="sm" className="hidden sm:block">
          <Menu className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-muted">
          {user?.org_id || "Default Org"}
        </span>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setExpanded(!expanded)}
          className="p-1 rounded-md hover:bg-surface-muted transition-colors"
        >
          <Bell className="h-4 w-4" />
          {user?.failed_login_attempts > 0 && (
            <span className="absolute -top -right -2 bg-status-critical text-xs text-white rounded-full h-4 w-4 flex items-center justify-center">
              {user?.failed_login_attempts}
            </span>
          )}
        </Button>

        <div className="hidden sm:block sm:w-px sm:bg-divider mx-3"></div>

        <Button
          variant="ghost"
          size="icon"
          onClick={handleLogout}
          className="p-1 rounded-md hover:bg-surface-muted transition-colors"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}