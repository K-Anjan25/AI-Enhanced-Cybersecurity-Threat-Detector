import type { ReactNode } from 'react';
import { useDocumentMeta } from './hooks';
import { SiteFooter } from './components/SiteFooter';
import { SiteHeader } from './components/SiteHeader';
import { StickyCta } from './components/StickyCta';

interface MarketingLayoutProps {
  title: string;
  description: string;
  children: ReactNode;
}

/**
 * Frame shared by every public page: skip link, header with hamburger menu, the page,
 * the sticky call-to-action and the footer. Each page supplies its own title and
 * description, so search results and link previews describe the page they point to.
 */
export function MarketingLayout({ title, description, children }: MarketingLayoutProps) {
  useDocumentMeta(title, description);
  return (
    <div className="marketing-site landing-backdrop flex min-h-screen flex-col overflow-x-hidden text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-40 focus:rounded-pill focus:bg-accent focus:px-6 focus:py-3 focus:text-onAccent"
      >
        Skip to content
      </a>
      <SiteHeader />
      <main id="main" tabIndex={-1} className="flex flex-1 flex-col focus:outline-none">
        {children}
      </main>
      <StickyCta />
      <SiteFooter />
    </div>
  );
}
