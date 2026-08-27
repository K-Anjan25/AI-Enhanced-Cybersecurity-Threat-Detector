import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Menu, X } from "lucide-react";
import BrandLogo from "../BrandLogo";
import { useScrollDirection } from "../../hooks";
import { cn } from "../ui";

/**
 * LandingNav — sticky header with the WooCommerce playbook: one brand lockup,
 * quiet anchor nav, one prominent CTA; hides while scrolling down, reveals on
 * scroll-up or at the top (`useScrollDirection`).
 */
const ANCHORS = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Why NOCTRA", href: "#why" },
] as const;

const LandingNav: React.FC = () => {
  const direction = useScrollDirection(12);
  const [open, setOpen] = React.useState(false);
  const hidden = direction === "down" && !open;

  return (
    <header
      className={cn(
        "sticky top-0 z-30 border-b border-line-subtle bg-app-bg/85 backdrop-blur-xl transition-transform duration-300",
        hidden && "-translate-y-full"
      )}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        <BrandLogo size={28} />

        <nav aria-label="Landing" className="hidden md:flex items-center gap-1">
          {ANCHORS.map((a) => (
            <a
              key={a.href}
              href={a.href}
              className="px-3.5 py-2 rounded-lg text-sm font-medium text-content-secondary hover:text-content-primary hover:bg-app-surface-raised transition"
            >
              {a.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Link
            to="/login"
            className="hidden sm:inline-flex px-4 py-2 rounded-lg bg-app-surface border border-line-subtle text-content-primary text-sm font-medium hover:bg-app-surface-raised transition"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="inline-flex items-center gap-1.5 px-4 sm:px-5 py-2 rounded-lg bg-brand-gradient text-brand-ink text-sm font-semibold hover:opacity-90 transition shadow-float"
          >
            Start free <ArrowRight size={15} aria-hidden />
          </Link>
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="md:hidden w-9 h-9 rounded-lg bg-app-surface border border-line-subtle text-content-secondary hover:text-content-primary transition flex items-center justify-center cursor-pointer"
          >
            {open ? <X size={16} aria-hidden /> : <Menu size={16} aria-hidden />}
          </button>
        </div>
      </div>

      {open && (
        <nav aria-label="Landing mobile" className="md:hidden border-t border-line-subtle bg-app-bg px-4 py-3 space-y-1 animate-fade-in">
          {ANCHORS.map((a) => (
            <a
              key={a.href}
              href={a.href}
              onClick={() => setOpen(false)}
              className="block px-3 py-2.5 rounded-lg text-sm font-medium text-content-secondary hover:text-content-primary hover:bg-app-surface-raised transition"
            >
              {a.label}
            </a>
          ))}
          <Link
            to="/login"
            onClick={() => setOpen(false)}
            className="block px-3 py-2.5 rounded-lg text-sm font-medium text-content-secondary hover:text-content-primary hover:bg-app-surface-raised transition"
          >
            Sign in
          </Link>
        </nav>
      )}
    </header>
  );
};

export default LandingNav;
