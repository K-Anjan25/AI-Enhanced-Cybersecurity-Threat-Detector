import React from "react";
import { Link } from "react-router-dom";
import { buttonVariants } from "../ui/Button";
import { cn } from "../ui/Button";
import { BRAND_NAME } from "../../constants/brand";

/**
 * FinalCTA — the access panel + footer, ported from newfile.html.
 * Green-bordered panel with a soft glow, then the minimal footer with the
 * live status line.
 */
const FinalCTA: React.FC = () => (
  <>
    <section id="access" className="mx-auto max-w-7xl scroll-mt-16 px-5 py-20 lg:px-8 lg:py-28">
      <div className="console-panel relative overflow-hidden rounded-sm p-8 sm:p-12">
        <div
          className="absolute right-0 top-0 h-40 w-40 bg-accent-primary/10 blur-3xl"
          aria-hidden="true"
        />
        <p className="tech-label text-accent-primary">See your environment differently</p>
        <h2 className="relative mt-4 max-w-2xl text-display-lg font-bold text-content-primary">
          Turn uncertainty into a security advantage.
        </h2>
        <p className="relative mt-5 max-w-xl leading-7 text-content-secondary">
          NOCTRA gives security teams the continuous context needed to find, validate, and
          neutralize emerging exposure.
        </p>
        <div className="relative mt-8 flex flex-wrap gap-3">
          <Link
            to="/register"
            className={cn(buttonVariants({ variant: "primary", size: "lg" }))}
          >
            Request access
          </Link>
          <Link
            to="/login"
            className={cn(buttonVariants({ variant: "secondary", size: "lg" }))}
          >
            Sign in
          </Link>
        </div>
      </div>
    </section>

    <footer className="border-t border-white/10">
      <div className="mx-auto flex max-w-7xl flex-col justify-between gap-4 px-5 py-7 text-sm text-content-tertiary sm:flex-row lg:px-8">
        <p>© 2026 {BRAND_NAME} — Threat intelligence, always on.</p>
        <p className="tech-label text-accent-primary">Systems nominal · 24/7</p>
      </div>
    </footer>
  </>
);

export default FinalCTA;
