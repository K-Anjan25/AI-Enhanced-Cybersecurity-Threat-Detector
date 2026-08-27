import { useEffect, useState } from "react";

/**
 * useScrollDirection — sticky-header pattern from the WooCommerce playbook:
 * hide the header while scrolling down (give content the space), reveal it the
 * instant the user scrolls up or nears the top. Reduces chrome when it matters.
 */
export function useScrollDirection(threshold = 8): "up" | "down" {
  const [direction, setDirection] = useState<"up" | "down">("up");

  useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;

    const update = () => {
      const y = window.scrollY;
      const delta = y - lastY;
      if (Math.abs(delta) > threshold) {
        setDirection(delta > 0 ? "down" : "up");
        lastY = y;
      }
      ticking = false;
    };

    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return direction;
}
