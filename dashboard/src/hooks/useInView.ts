import { useEffect, useRef, useState } from "react";

/**
 * useInView — fires `once` when the element scrolls into view. Powers the
 * reveal-on-scroll entrances of landing sections (IntersectionObserver,
 * reduced-motion safe: `rootMargin` only governs the reveal, content is always
 * readable regardless).
 */
export function useInView<T extends HTMLElement = HTMLDivElement>(
  options: IntersectionObserverInit = { rootMargin: "0px 0px -10% 0px" },
  once = true
): [React.RefObject<T>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) obs.unobserve(entry.target);
        } else if (!once) {
          setInView(false);
        }
      });
    }, options);
    obs.observe(el);
    return () => obs.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return [ref as React.RefObject<T>, inView];
}
