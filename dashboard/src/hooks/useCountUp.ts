import { useEffect, useRef, useState } from "react";

/**
 * useCountUp — animates a number toward `target` once `start` flips true.
 * Used for the landing proof strip (e.g. "114 tests passing") so numbers land
 * with presence but respect reduced motion (instant set).
 */
export function useCountUp(target: number, start: boolean, duration = 900): number {
  const [value, setValue] = useState(start ? target : 0);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!start) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - t0) / duration, 1);
      // easeOutCubic — quick start, gentle landing
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(target * eased));
      if (p < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [start, target, duration]);

  return value;
}
