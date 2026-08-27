import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import BrandLogo from "../BrandLogo";
import ThemeToggle from "../ThemeToggle";
import { cn } from "../ui";

/**
 * LandingNav — Apple product-page header: floating translucent pill, centered
 * brand, hairline glass border, one gradient CTA. Hides on scroll-down.
 */
const ANCHORS = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Why NOCTRA", href: "#why" },
] as const;

export default function LandingNav() {
  const [scrolled, setScrolled] = React.useState(false);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(() => {
          const y = window.scrollY;
          setScrolled(y > 8 && y > lastY);
          lastY = y;
          ticking = false;
        });
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-40 flex justify-center px-4 pt-3 pointer-events-none">
      <div
        className={cn(
          "pointer-events-auto flex items-center gap-2 sm:gap-4 rounded-full border border-line-subtle bg-app-surface/80 backdrop-blur-xl shadow-float px-3 sm:px-4 h-12 transition-transform duration-300",
          scrolled && "-translate-y-24"
        )}
      >
        <Link to="/" className="flex items-center pl-1 hover:opacity-80 transition" aria-label="NOCTRA home">
          <span className="hidden sm:inline-flex">
            <BrandLogo size={22} />
          </span>
          <span className="sm:hidden inline-flex">
            <BrandLogo size={22} withWordmark={false} />
          </span>
        </Link>

        <nav aria-label="Landing" className="hidden md:flex items-center gap-0.5 ml-2">
          {ANCHORS.map((a) => (
            <a
              key={a.href}
              href={a.href}
              className="px-3.5 py-1.5 rounded-full text-[13px] font-medium text-content-secondary hover:text-content-primary hover:bg-app-subtle transition"
            >
              {a.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2 md:ml-2">
          <ThemeToggle variant="pill" />
          <Link
            to="/login"
            className="hidden sm:inline-flex px-3.5 py-1.5 rounded-full text-[13px] font-medium text-content-secondary hover:text-content-primary hover:bg-app-subtle transition"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="inline-flex items-center gap-1.5 px-4 sm:px-5 py-2 rounded-full bg-brand-gradient text-brand-ink text-[13px] font-semibold hover:opacity-90 transition shadow-float"
          >
            Start free <ArrowRight size={14} aria-hidden />
          </Link>
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            className="md:hidden w-9 h-9 rounded-full flex items-center justify-center text-content-secondary hover:bg-app-subtle transition cursor-pointer"
          >
            {open ? "✕" : "☰"}
          </button>
        </div>
      </div>

      {open && (
        <nav
          aria-label="Landing mobile"
          className="pointer-events-auto md:hidden absolute top-16 w-[calc(100%-2rem)] max-w-sm rounded-3xl border border-line-subtle bg-app-surface/95 backdrop-blur-xl shadow-overlay p-3 animate-scale-in"
        >
          {ANCHORS.map((a) => (
            <a
              key={a.href}
              href={a.href}
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 rounded-2xl text-sm font-medium text-content-primary hover:bg-app-subtle transition"
            >
              {a.label}
            </a>
          ))}
          <Link
            to="/login"
            onClick={() => setOpen(false)}
            className="block px-4 py-2.5 rounded-2xl text-sm font-medium text-content-primary hover:bg-app-subtle transition"
          >
            Sign in
          </Link>
        </nav>
      )}
    </header>
  );
}
