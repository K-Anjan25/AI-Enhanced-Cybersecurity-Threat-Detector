/**
 * Design tokens as Tailwind theme hooks (rules R-27, T-401).
 *
 * Every value here mirrors design.md §5. Colours live as CSS variables in
 * src/index.css so both themes share one set of names; this file maps those
 * variables onto utilities.
 *
 * Two structural choices make the token layer a closed system, and both are
 * asserted by src/theme/tailwind.test.ts rather than left as intent:
 *
 *   * `theme.colors` and `theme.spacing` *replace* Tailwind's defaults instead
 *     of extending them. An off-token class therefore compiles to nothing at
 *     all: `bg-red-500` and `p-5` produce no CSS, so a stray palette colour or
 *     an off-scale spacing value cannot reach a screen even by accident. Extend
 *     is used only for the scales design.md adds to (density, icons, rail,
 *     elevation), which have no default worth keeping.
 *   * Colours are `var(--…)` references and nothing else, so a theme switch is
 *     a change of attribute rather than a rebuild, and the contrast suite has
 *     exactly one file to read.
 */
/**
 * The colour scale, named once. The scales below reuse it rather than restating
 * it, because overriding a Tailwind scale to change its DEFAULT also *removes* the
 * scale: `border-color: { DEFAULT: … }` alone would delete `border-line`.
 */
const colors = {
  transparent: 'transparent',
  current: 'currentColor',
  inherit: 'inherit',

  base: 'var(--color-bg-base)',
  surface: 'var(--color-bg-surface)',
  line: 'var(--color-border)',
  ink: 'var(--color-text-primary)',
  muted: 'var(--color-text-muted)',
  accent: 'var(--color-accent)',
  // Text that sits *on* a fill rather than on a surface: the badge rule's
  // near-black (§5.3) and the primary button's on-accent. Both variables existed
  // in index.css from the start; without a utility here the badge rule had no way
  // to be written (T-402 found that).
  onAccent: 'var(--color-on-accent)',
  onSeverity: 'var(--color-on-severity)',
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
};

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  // Without this flag Tailwind resolves `--tw-ring-color` by *compositing*
  // ringColor.DEFAULT with the default ring opacity, and since the default is a
  // `var()` it cannot composite — it writes the hardcoded fallback
  // `rgb(147 197 253 / 0.5)` (blue-300) into the stylesheet instead. The flag
  // makes the variable the token itself, which is also how Tailwind v4 behaves.
  future: {
    respectDefaultRingColorOpacity: true,
  },
  theme: {
    // No default palette: an off-token colour must not compile. `transparent`,
    // `currentColor` and `inherit` stay because they are not colours from a
    // palette — they are the surrounding context, and a border that inherits
    // is still on-token.
    colors,
    // A hairline is the border token, so a bare `border` is on-token too.
    // Tailwind's default here is `gray-200`, which no longer exists.
    borderColor: {
      DEFAULT: colors.line,
      ...colors,
    },
    // Tailwind's ring defaults are blue-500 at 50% with a white offset, which
    // would put an off-token colour in the stylesheet and a halo nobody chose on
    // the first `focus:ring`. The system has one focus treatment — the accent
    // ring in src/index.css (design.md §5.3) — so `ring` defaults to it.
    ringColor: {
      DEFAULT: 'var(--focus-ring)',
      ...colors,
    },
    ringOffsetColor: {
      DEFAULT: colors.base,
      ...colors,
    },
    // The placeholder default is gray-400, which this palette no longer has;
    // muted text is what design.md §5.1 uses for secondary copy.
    placeholderColor: {
      DEFAULT: colors.muted,
      ...colors,
    },
    // design.md §8.3's three breakpoints and nothing else (T-412). Like the colour
    // and spacing scales, this *replaces* Tailwind's defaults rather than extending
    // them: `sm:` (640 px) and `2xl:` (1536 px) are not in the design, so they now
    // compile to nothing instead of quietly defining a fourth and fifth breakpoint
    // that no document mentions. The three numbers are asserted against §8.3's table
    // by src/theme/tailwind.test.ts, which is what stops them drifting.
    screens: {
      md: '768px',
      lg: '1024px',
      xl: '1440px',
    },
    // design.md §5.4's two stacks and nothing else. `font-serif` emits nothing:
    // a third stack would be a decision, and the document names two.
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
    },
    // The documented type scale and nothing else, so the 12px floor cannot be
    // undercut by a Tailwind default step (`text-xs` is exactly 12px, but
    // `text-sm`/`text-base` are steps nobody published a line-height for).
    fontSize: {
      display: ['32px', { lineHeight: '36px', fontWeight: '600' }],
      h1: ['24px', { lineHeight: '32px', fontWeight: '600' }],
      h2: ['18px', { lineHeight: '26px', fontWeight: '600' }],
      body: ['14px', { lineHeight: '20px', fontWeight: '400' }],
      'body-sm': ['13px', { lineHeight: '18px', fontWeight: '400' }],
      caption: ['12px', { lineHeight: '16px', fontWeight: '400' }],
    },
    // The documented 4px scale and nothing else: 4, 8, 12, 16, 24, 32, 48, 64.
    // `0` is kept because zero is the absence of a step, not a step
    // (design.md §5.5, "No off-scale values").
    spacing: {
      0: '0px',
      1: '4px',
      2: '8px',
      3: '12px',
      4: '16px',
      6: '24px',
      8: '32px',
      12: '48px',
      16: '64px',
    },
    extend: {
      borderRadius: {
        input: '4px',
        card: '8px',
        modal: '12px',
        pill: '999px',
      },
      // Elevation is reserved for overlays (design.md §5.5), so this is the only
      // shadow in the system and there is nothing to reach for otherwise.
      boxShadow: {
        overlay: 'var(--shadow-overlay)',
      },
      // Icon sizes (design.md §5.6): dense contexts and elsewhere.
      size: {
        'icon-sm': '16px',
        'icon-md': '20px',
      },
      // Density modes (design.md §5.5). Row height is a table property, so it
      // belongs beside `spacing` rather than inside it: it is not a step.
      height: {
        // §3's top bar, then §5.5's two density rows.
        topbar: '56px',
        'row-comfortable': '44px',
        'row-compact': '32px',
      },
      // The 3px severity rail (design.md §5.3).
      borderWidth: {
        rail: '3px',
      },
      // Motion (design.md §8.2), authored in index.css so the reduced-motion guard
      // sits beside the values it guards.
      transitionDuration: {
        micro: 'var(--duration-micro)',
        panel: 'var(--duration-panel)',
        page: 'var(--duration-page)',
      },
      // Layout widths from design.md §3: "persistent 240 px left rail (collapsible
      // to a 56 px icon rail) + a 56 px top bar". They were inline styles in
      // AppShell because §5's spacing scale has no step for them and should not
      // grow one: these are layout dimensions, not spacing.
      width: {
        rail: '240px',
        'rail-collapsed': '56px',
      },
    },
  },
  plugins: [],
};
