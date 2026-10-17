import { Activity, ArrowRight, Search, ShieldCheck, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

import heroImage from '../../assets/landing-hero.jpg';

const FEATURES: ReadonlyArray<{ title: string; icon: LucideIcon }> = [
  { title: 'Detect', icon: Activity },
  { title: 'Triage', icon: ShieldCheck },
  { title: 'Hunt', icon: Search },
];

/** The public front page, shown at `/` to anyone without a session. */
export function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col bg-base text-ink">
      <header className="flex h-topbar items-center justify-between px-6 md:px-12">
        <span className="text-h2 uppercase tracking-widest">AEGIS</span>
        <Link
          to="/sign-in"
          className="rounded-input border border-line px-4 py-1 text-caption hover:bg-surface"
        >
          Sign in
        </Link>
      </header>

      <section className="grid flex-1 items-center gap-10 px-6 py-12 md:grid-cols-2 md:px-12">
        <div>
          <h1 className="text-display uppercase leading-tight">Protect your data</h1>
          <Link
            to="/sign-in"
            className="mt-8 inline-flex items-center gap-2 rounded-input bg-accent px-6 py-2 font-semibold text-onAccent"
          >
            Get protected
            <ArrowRight aria-hidden="true" className="size-icon-sm" />
          </Link>
        </div>
        <img src={heroImage} alt="" className="mx-auto w-full max-w-xl rounded-card object-cover" />
      </section>

      <section className="grid grid-cols-1 gap-4 border-t border-dashed border-line px-6 py-10 md:grid-cols-3 md:px-12">
        {FEATURES.map(({ title, icon: Icon }) => (
          <article key={title} className="rounded-card border border-line bg-surface p-6">
            <Icon aria-hidden="true" className="size-icon-md text-accent" />
            <h2 className="mt-4 text-h2 uppercase tracking-wider">{title}</h2>
          </article>
        ))}
      </section>
    </main>
  );
}
