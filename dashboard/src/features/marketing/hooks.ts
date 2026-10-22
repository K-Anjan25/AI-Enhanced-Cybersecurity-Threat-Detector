import { useEffect, type RefObject } from 'react';

/** Animations skip straight to their end state for users who ask for reduced motion. */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

/** Keeps the page title and meta description in step with the current page (SEO). */
export function useDocumentMeta(title: string, description: string): void {
  useEffect(() => {
    document.title = title;
    document.querySelector('meta[name="description"]')?.setAttribute('content', description);
  }, [title, description]);
}

/**
 * Writes `--scroll` (scroll position in 100 px steps) onto the element, once per frame.
 * The hero's depth layers read it, so each layer moves at its own speed.
 */
export function useScrollDepth(ref: RefObject<HTMLElement>): void {
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    let frame = 0;
    const update = () => {
      frame = 0;
      element.style.setProperty('--scroll', String(window.scrollY / 100));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ref]);
}
