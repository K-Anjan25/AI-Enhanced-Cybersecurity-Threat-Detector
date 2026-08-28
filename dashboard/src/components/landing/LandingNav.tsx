import React from "react";
import { Link } from "react-router-dom";
import { buttonVariants } from "../ui/Button";
import { cn } from "../ui/Button";

/**
 * LandingNav — ported from newfile.html (NOCTRA Signal).
 * Sticky blur header: signal-dot brand lockup, anchor links, one green
 * action. No theme toggle — the landing is the ink canvas by design.
 */
const ANCHORS = [
  { href: "#platform", label: "Platform" },
  { href: "#console", label: "Console" },
  { href: "#intelligence", label: "Intelligence" },
];

const LandingNav: React.FC = () => (
  <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-app-bg/85 backdrop-blur-md">
    <nav
      className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8"
      aria-label="Main navigation"
    >
      <Link to="/welcome" className="flex items-center gap-3" aria-label="NOCTRA home">
        <span className="signal-dot" aria-hidden="true" />
        <span className="text-[15px] font-bold font-display tracking-[0.22em] uppercase text-content-primary">
          NOCTRA
        </span>
      </Link>

      <div className="hidden items-center gap-8 md:flex">
        {ANCHORS.map((a) => (
          <a
            key={a.href}
            href={a.href}
            className="text-sm text-content-secondary transition-colors hover:text-accent-primary"
          >
            {a.label}
          </a>
        ))}
      </div>

      <Link
        to="/register"
        className={cn(buttonVariants({ variant: "primary", size: "md" }), "text-sm")}
      >
        Request access
      </Link>
    </nav>
  </header>
);

export default LandingNav;
