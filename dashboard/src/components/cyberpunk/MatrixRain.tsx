/**
 * MatrixRain — Full-screen canvas-based cyberpunk matrix rain effect.
 *
 * Renders falling characters (katakana, hex digits, binary) on a transparent
 * canvas overlay. Designed to sit behind the main content as an ambient
 * background layer. Respects prefers-reduced-motion.
 */
import { useEffect, useRef } from 'react';

const CHAR_SETS = [
  '01',
  '0123456789ABCDEF',
  'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン',
  '{}[]<>/\\|=+-*&^%$#@!~',
];

export function MatrixRain({ opacity = 0.08 }: { opacity?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Respect reduced-motion
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    let animId: number;
    let columns: number;
    let drops: number[];
    const fontSize = 14;

    function resize() {
      canvas!.width = window.innerWidth;
      canvas!.height = window.innerHeight;
      columns = Math.floor(canvas!.width / fontSize);
      drops = Array.from({ length: columns }, () =>
        Math.random() * -100,
      );
    }

function randomChar(): string {
  const set = CHAR_SETS[Math.floor(Math.random() * CHAR_SETS.length)] ?? '01';
  return set[Math.floor(Math.random() * set.length)] ?? '0';
}

    function draw() {
      if (!ctx || !canvas) return;
      // Fade trail
      ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let i = 0; i < columns; i++) {
        const char = randomChar();
        const x = i * fontSize;
        const y = (drops[i] ?? 0) * fontSize;

        // Head glow
        ctx.font = `${fontSize}px "JetBrains Mono", monospace`;
        ctx.fillStyle = 'rgba(0, 240, 255, 0.9)';
        ctx.shadowColor = '#00f0ff';
        ctx.shadowBlur = 8;
        ctx.fillText(char, x, y);

        // Trail
        ctx.shadowBlur = 0;
        ctx.fillStyle = 'rgba(0, 240, 255, 0.15)';
        for (let t = 1; t < 8; t++) {
          const trailChar = randomChar();
          ctx.fillText(trailChar, x, y - t * fontSize);
        }

        if (y > canvas.height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i] = (drops[i] ?? 0) + 0.5 + Math.random() * 0.5;
      }

      animId = requestAnimationFrame(draw);
    }

    resize();
    draw();
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