import React from "react";
import { CheckCircle2, ShieldCheck, ScrollText } from "lucide-react";
import BrandLogo from "../../../components/BrandLogo";
import { ThemeToggle } from "../../../components/ThemeToggle";

/**
 * AuthLayout — shared shell for the sign-in / sign-up screens, in the
 * NOCTRA Signal system (newfile.html):
 *   left  — brand panel on the ink canvas: signal-dot mark, tech-label
 *           overline, big tight display headline, three product truths.
 *   right — the form card on the grid-textured canvas.
 * The auth surface is the ink canvas by design (no theme toggle).
 */
export interface AuthLayoutProps {
  headline: React.ReactNode;
  subhead: string;
  children: React.ReactNode;
}

const FEATURES = [
  {
    icon: CheckCircle2,
    title: "Review decisions",
    body: "One reversible action per case, explained in plain English.",
  },
  {
    icon: ShieldCheck,
    title: "Investigate cases",
    body: "Blast radius, affected systems, and stated confidence — not alarms.",
  },
  {
    icon: ScrollText,
    title: "Record every step",
    body: "Append-only audit trail. NOCTRA records actions, never executes them.",
  },
] as const;

const AuthLayout: React.FC<AuthLayoutProps> = ({ headline, subhead, children }) => {
  return (
    <div className="night noctra-canvas relative min-h-screen lg:flex">
      {/* Brand panel (desktop) */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 px-12 py-10 border-r border-white/10">
        <BrandLogo size={44} />

        <div className="max-w-md">
          <p className="tech-label text-accent-primary">Threat intelligence, always on</p>
          <h1 className="mt-5 font-display font-semibold text-[2.5rem] leading-[1.05] tracking-[-0.035em] text-content-primary text-balance">
            {headline}
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-content-secondary">{subhead}</p>

          <div className="mt-9 flex flex-col gap-2.5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="flex items-start gap-3 rounded-sm border border-line-subtle bg-app-surface/60 px-4 py-3"
              >
                <f.icon size={15} className="mt-0.5 text-accent-primary shrink-0" aria-hidden />
                <div>
                  <p className="text-[13px] font-semibold text-content-primary">{f.title}</p>
                  <p className="text-xs text-content-tertiary leading-relaxed mt-0.5">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="tech-label text-content-tertiary">
          NOCTRA — threat intelligence, always on · noctra.ai
        </p>
      </div>

      {/* Form side */}
      <div className="flex-1 flex items-center justify-center px-4 py-14 lg:py-10 min-h-screen lg:min-h-0">
        {children}
      </div>
    </div>
  );
};

export default AuthLayout;
