import { useEffect, useRef, useState, type ReactNode } from 'react';
import { prefersReducedMotion } from '../hooks';

interface RevealProps {
  children: ReactNode;
  /** Delay before the fade starts, in milliseconds, so neighbours can stagger. */
  delayMs?: number;
  className?: string;
}

/**
 * Fades its children up once they scroll into view. Without IntersectionObserver, or
 * with reduced motion, the content is shown at once.
 */
export function Reveal({ children, delayMs = 0, className = '' }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    if (!('IntersectionObserver' in window) || prefersReducedMotion()) {
      setVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`marketing-reveal ${visible ? 'is-visible' : ''} ${className}`.trim()}
      style={{ transitionDelay: `${delayMs}ms` }}
    >
      {children}
    </div>
  );
}
