import React from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, Activity } from "lucide-react";
import { buttonVariants } from "../ui/Button";
import { cn } from "../ui/Button";
import { BRAND_HERO_LINE } from "../../constants/brand";

/**
 * LandingHero — ported from newfile.html (NOCTRA Signal).
 * Left: hero-line eyebrow, huge tight headline, two CTAs, proof items.
 * Right: HUD-bracketed threat-topology frame (built in SVG — the repo rule
 * of no stock art stands; the frame carries the design's corner brackets).
 */
const scrollTo = (id: string) => () => {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
};

const LandingHero: React.FC = () => (
  <section className="mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-16 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:px-8 lg:pb-28 lg:pt-24">
    <div>
      <div className="animate-reveal flex items-center gap-3">
        <span className="h-px w-[88px] bg-gradient-to-r from-accent-primary to-transparent" aria-hidden />
        <p className="tech-label text-accent-primary">Autonomous threat intelligence</p>
      </div>

      <h1 className="animate-reveal animate-delay-1 mt-7 max-w-3xl text-display-2xl font-bold text-content-primary">
        {BRAND_HERO_LINE}
      </h1>

      <p className="animate-reveal animate-delay-2 mt-7 max-w-xl text-base leading-7 text-content-secondary sm:text-lg">
        NOCTRA continuously maps your attack surface, detects what matters, and turns
        fragmented signals into decisive action.
      </p>

      <div className="animate-reveal animate-delay-3 mt-9 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={scrollTo("console")}
          className={cn(buttonVariants({ variant: "primary", size: "lg" }))}
        >
          Explore the console
        </button>
        <Link
          to="/register"
          className={cn(buttonVariants({ variant: "secondary", size: "lg" }))}
        >
          Request access
        </Link>
      </div>

      <div className="mt-12 flex flex-wrap gap-x-8 gap-y-4 text-content-secondary">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-accent-primary" aria-hidden="true" />
          <span className="text-sm">Always-on coverage</span>
        </div>
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent-primary" aria-hidden="true" />
          <span className="text-sm">AI-prioritized signals</span>
        </div>
      </div>
    </div>

    {/* Threat topology frame — HUD corner brackets (newfile .hero-image-wrap). */}
    <div className="animate-reveal animate-delay-2 hud-corners relative min-h-[320px] overflow-hidden rounded-sm border border-accent-primary/25 bg-app-void shadow-hero">
      <svg
        viewBox="0 0 520 400"
        className="h-full w-full"
        preserveAspectRatio="xMidYMid slice"
        aria-label="Illustrative threat topology — signals connected across an environment"
        role="img"
      >
        {/* signal links */}
        <g stroke="#a6ff3f" strokeOpacity="0.22" strokeWidth="1">
          <path d="M260 200 L120 96" />
          <path d="M260 200 L412 84" />
          <path d="M260 200 L428 268" />
          <path d="M260 200 L112 262" />
          <path d="M120 96 L84 196" />
          <path d="M412 84 L468 176" />
          <path d="M428 268 L336 330" />
          <path d="M112 262 L188 336" />
          <path d="M336 330 L428 268" />
        </g>
        {/* nodes */}
        <g fill="#a6ff3f">
          <circle cx="260" cy="200" r="9" />
          <circle cx="120" cy="96" r="4.5" fillOpacity="0.85" />
          <circle cx="412" cy="84" r="4.5" fillOpacity="0.85" />
          <circle cx="428" cy="268" r="4.5" fillOpacity="0.85" />
          <circle cx="112" cy="262" r="4.5" fillOpacity="0.85" />
          <circle cx="84" cy="196" r="3" fillOpacity="0.5" />
          <circle cx="468" cy="176" r="3" fillOpacity="0.5" />
          <circle cx="336" cy="330" r="4.5" fillOpacity="0.85" />
          <circle cx="188" cy="336" r="3" fillOpacity="0.5" />
        </g>
        {/* halo rings on the hub */}
        <circle cx="260" cy="200" r="18" fill="none" stroke="#a6ff3f" strokeOpacity="0.35" />
        <circle cx="260" cy="200" r="30" fill="none" stroke="#a6ff3f" strokeOpacity="0.14" />
        {/* scan sweep */}
        <line x1="0" y1="140" x2="520" y2="140" stroke="#a6ff3f" strokeOpacity="0.35" strokeWidth="1" className="animate-pulse" />
        <line x1="0" y1="290" x2="520" y2="290" stroke="#a6ff3f" strokeOpacity="0.18" strokeWidth="1" />
      </svg>

      <div className="absolute bottom-0 left-0 z-[3] p-6">
        <p className="tech-label text-accent-primary">Threat topology / live</p>
        <p className="mt-2 max-w-xs text-sm text-white">
          A connected view of every signal across your environment.
        </p>
      </div>
    </div>
  </section>
);

export default LandingHero;
