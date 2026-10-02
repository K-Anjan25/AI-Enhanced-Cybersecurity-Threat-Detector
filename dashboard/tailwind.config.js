/**
 * Design tokens as Tailwind theme extensions.
 *
 * Every value here mirrors design.md §5. Colours are defined as CSS variables in
 * src/index.css so the light and dark themes share one set of names; this file
 * only maps those variables onto Tailwind utilities (rules R-27, T-401).
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        base: 'var(--color-bg-base)',
        surface: 'var(--color-bg-surface)',
        line: 'var(--color-border)',
        ink: 'var(--color-text-primary)',
        muted: 'var(--color-text-muted)',
        accent: 'var(--color-accent)',
        severity: {
          critical: 'var(--severity-critical)',
          high: 'var(--severity-high)',
          medium: 'var(--severity-medium)',
          low: 'var(--severity-low)',
          info: 'var(--severity-info)',
          benign: 'var(--severity-benign)',
        },
        // For text rendered directly on a surface. The base severity hues fail
        // WCAG AA as text in the light theme — see design.md §5.3.
        severityText: {
          critical: 'var(--severity-text-critical)',
          high: 'var(--severity-text-high)',
          medium: 'var(--severity-text-medium)',
          low: 'var(--severity-text-low)',
          info: 'var(--severity-text-info)',
          benign: 'var(--severity-text-benign)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        // design.md §5.4 — caption is the floor at 12px.
        display: ['32px', { lineHeight: '36px', fontWeight: '600' }],
        h1: ['24px', { lineHeight: '32px', fontWeight: '600' }],
        h2: ['18px', { lineHeight: '26px', fontWeight: '600' }],
        body: ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'body-sm': ['13px', { lineHeight: '18px', fontWeight: '400' }],
        caption: ['12px', { lineHeight: '16px', fontWeight: '400' }],
      },
      spacing: {
        // 4px scale only (design.md §5.5). No off-scale values.
        1: '4px',
        2: '8px',
        3: '12px',
        4: '16px',
        6: '24px',
        8: '32px',
        12: '48px',
        16: '64px',
      },
      borderRadius: {
        input: '4px',
        card: '8px',
        modal: '12px',
        pill: '999px',
      },
    },
  },
  plugins: [],
};
