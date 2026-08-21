import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { logout } from "../../store/userActions";
import { Search, Bell, Settings, LogOut, ShieldCheck } from "lucide-react";
import BrandLogo from "../BrandLogo";

export interface NavbarProps {
  onLogout?: () => void;
}

const Navbar: React.FC<NavbarProps> = ({ onLogout }) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState<boolean>(false);
  const [search, setSearch] = useState<string>("");
  const navigate = useNavigate();
  const dispatch = useDispatch();

  const username: string = localStorage.getItem("username") || "User";
  const userRole: string = (localStorage.getItem("user_role") || "user").toLowerCase();

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
    <header className="h-16 bg-app-surface border-b border-line-subtle flex items-center justify-between px-6 shrink-0 z-20 w-full">
      <div className="flex items-center gap-4">
        <Link to="/" className="flex items-center hover:opacity-90 transition">
          <BrandLogo size={26} />
        </Link>

        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-status-success/10 text-status-success border border-status-success/20">
          <span className="w-1.5 h-1.5 rounded-full bg-status-success animate-pulse"></span>
          LIVE STREAM
        </span>
      </div>

      <div className="w-80 max-w-[40%]">
        <div className="relative">
          <Search size={14} className="absolute inset-y-0 left-3 my-auto text-content-tertiary" aria-hidden />
          <input
            type="text"
            placeholder="Search IP, threat, hash…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            className="w-full bg-app-bg text-sm text-content-primary pl-9 pr-4 py-2 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition placeholder-content-tertiary"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Notifications"
          title="Notifications"
          className="relative w-9 h-9 rounded-lg bg-app-subtle border border-line-subtle text-content-secondary hover:text-content-primary hover:bg-line-bright transition flex items-center justify-center cursor-pointer"
        >
          <Bell size={16} aria-hidden />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-status-critical" />
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
            aria-expanded={isProfileMenuOpen}
            aria-haspopup="menu"
            className="w-9 h-9 rounded-full bg-accent-primary text-app-bg font-bold flex items-center justify-center hover:bg-accent-glow transition ring-2 ring-accent-primary/20 cursor-pointer"
          >
            {username.charAt(0).toUpperCase()}
          </button>

          {isProfileMenuOpen && (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-56 bg-app-surface border border-line-subtle rounded-xl shadow-overlay py-2 z-50 animate-scale-in"
            >
              <div className="px-4 py-2.5 border-b border-line-subtle flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-accent-primary text-app-bg flex items-center justify-center font-bold text-xs shrink-0">
                  {username.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-content-primary truncate">{username}</p>
                  <p className="text-xs text-accent-primary capitalize flex items-center gap-1">
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