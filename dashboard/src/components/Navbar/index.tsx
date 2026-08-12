import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { logout } from "../../store/userActions";

export interface NavbarProps {
  onLogout?: () => void;
}

const Navbar: React.FC<NavbarProps> = ({ onLogout }) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState<boolean>(false);
  const navigate = useNavigate();
  const dispatch = useDispatch();

  const username: string = localStorage.getItem("username") || "User";
  const userRole: string = (localStorage.getItem("user_role") || "user").toLowerCase();

  const handleLogout = (): void => {
    setIsProfileMenuOpen(false);
    // Reset the Redux auth state (clears tokens + user) before redirecting,
    // otherwise Login's useEffect sees stale isLogedIn=true and bounces back.
    dispatch(logout() as any);
    onLogout?.();
    navigate("/login");
  };

  return (
    <header className="h-16 bg-app-surface border-b border-line-subtle flex items-center justify-between px-6 shrink-0 z-20 w-full">
      <div className="flex items-center gap-4">
        <Link to="/alerts" className="flex items-center gap-2 group">
          <span className="text-xl font-bold text-accent-primary">TD</span>
          <span className="text-lg font-bold text-content-primary tracking-tight">
            ThreatDetector<span className="text-accent-primary">AI</span>
          </span>
        </Link>

        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-status-success border border-emerald-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-status-success animate-pulse"></span>
          LIVE STREAM
        </span>
      </div>

      <div className="w-80">
        <div className="relative">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-content-tertiary text-xs font-semibold">
            SRCH
          </span>
          <input
            type="text"
            placeholder="Search IP, threat, hash..."
            className="w-full bg-app-bg text-sm text-content-primary pl-12 pr-4 py-1.5 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition placeholder-content-tertiary"
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
            className="w-9 h-9 rounded-full bg-accent-primary text-app-bg font-bold flex items-center justify-center hover:bg-accent-glow transition ring-2 ring-accent-primary/20"
          >
            {username.charAt(0).toUpperCase()}
          </button>

          {isProfileMenuOpen && (
            <div className="absolute right-0 mt-2 w-52 bg-app-surface border border-line-subtle rounded-xl shadow-2xl py-2 z-50">
              <div className="px-4 py-2 border-b border-line-subtle">
                <p className="text-sm font-semibold text-content-primary truncate">
                  {username}
                </p>
                <p className="text-xs text-accent-primary capitalize">
                  {userRole}
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setIsProfileMenuOpen(false);
                  navigate("/profile");
                }}
                className="w-full text-left px-4 py-2 text-sm text-content-secondary hover:bg-app-subtle hover:text-accent-primary transition flex items-center gap-2"
              >
                <span className="text-xs font-semibold">SET</span> Settings
              </button>

              <button
                type="button"
                onClick={handleLogout}
                className="w-full text-left px-4 py-2 text-sm text-status-critical hover:bg-app-subtle transition flex items-center gap-2"
              >
                <span className="text-xs font-semibold">OUT</span> Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Navbar;
