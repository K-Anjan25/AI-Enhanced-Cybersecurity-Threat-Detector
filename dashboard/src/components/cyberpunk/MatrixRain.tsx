/**
 * MatrixRain — Lightweight canvas-based cyberpunk matrix rain effect.
 *
 * Optimized for low RAM: uses a single requestAnimationFrame loop,
 * limited column count, and short trail length. Respects prefers-reduced-motion.
 */
import { useEffect, useRef } from 'react';

const CHARS = '01アイウエオカキクケコ{}[]<>';

export function MatrixRain({ opacity = 0.08 }: { opacity?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    // Canvas cannot read CSS var(), so resolve the theme tokens to hex once per mount.
    const rootStyle = getComputedStyle(document.documentElement);
    const baseColour = rootStyle.getPropertyValue('--color-bg-base').trim();
    const accentColour = rootStyle.getPropertyValue('--color-accent').trim();

    let animId: number;
    let columns: number;
    let drops: number[];
    const fontSize = 16; // bigger = fewer columns = less memory
    let lastTime = 0;

    function resize() {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
      columns = Math.floor(canvas!.width / fontSize);
      drops = Array.from({ length: columns }, () => Math.random() * -50);
    }

    function draw(time: number) {
      // Throttle to ~20fps instead of 60fps
      if (time - lastTime < 50) {
        animId = requestAnimationFrame(draw);
        return;
      }
      lastTime = time;

      if (!ctx || !canvas) return;

      // Fade trail
      ctx.fillStyle = baseColour;
      ctx.globalAlpha = 0.07;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.font = `${fontSize}px monospace`;

      for (let i = 0; i < columns; i++) {
        const char = CHARS[Math.floor(Math.random() * CHARS.length)] ?? '0';
        const x = i * fontSize;
        const y = (drops[i] ?? 0) * fontSize;

        // Head glow
        ctx.fillStyle = accentColour;
        ctx.globalAlpha = 0.8;
        ctx.fillText(char, x, y);

        // Short trail (3 instead of 8)
        ctx.globalAlpha = 0.1;
        for (let t = 1; t < 3; t++) {
          ctx.fillText(CHARS[Math.floor(Math.random() * CHARS.length)] ?? '0', x, y - t * fontSize);
        }

        if (y > canvas.height && Math.random() > 0.98) {
          drops[i] = 0;
        }
        drops[i] = (drops[i] ?? 0) + 0.5 + Math.random() * 0.3;
      }

      animId = requestAnimationFrame(draw);
    }

    resize();
    animId = requestAnimationFrame(draw);
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0"
      style={{ opacity }}
      aria-hidden="true"
    />
  );
}
