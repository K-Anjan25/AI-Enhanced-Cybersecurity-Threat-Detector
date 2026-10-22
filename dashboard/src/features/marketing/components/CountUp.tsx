import { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from '../hooks';

interface CountUpProps {
  to: number;
  suffix?: string | undefined;
  durationMs?: number;
}

/**
 * Counts from zero to `to` once, when the element first scrolls into view. The moving
 * number is hidden from assistive technology; a screen-reader-only span announces the
 * final value once, so the count does not chatter.
 */
export function CountUp({ to, suffix = '', durationMs = 1600 }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    let started = false;
    let frame = 0;

    const run = () => {
      if (started) return;
      started = true;
      if (prefersReducedMotion()) {
        setValue(to);
        return;
      }
      const start = performance.now();
      const step = (now: number) => {
        const progress = Math.min(1, (now - start) / durationMs);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        setValue(Math.round(to * eased));
        if (progress < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    };

    if (!('IntersectionObserver' in window)) {
      run();
      return () => cancelAnimationFrame(frame);
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          run();
          observer.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [to, durationMs]);

  return (
    <span ref={ref}>
      <span aria-hidden="true">
        {value.toLocaleString('en-US')}
        {suffix}
      </span>
      <span className="sr-only">
        {to.toLocaleString('en-US')}
        {suffix}
      </span>
    </span>
  );
}
