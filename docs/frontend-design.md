# Frontend Design System

## 1. Color Palette — "Slate Indigo Dark" (Professional Minimalist)

**Philosophy**: Dark-mode-first for night-shift SOC analysts, high contrast, WCAG AA compliant, single accent color to reduce cognitive load. All colors are named by role, not hex, so they can be swapped thematically later.

### Semantic Tokens (Tailwind CSS `theme().colors`)

| Token                | Light (day)           | Dark (night)         | Usage                                      |
|----------------------|-----------------------|----------------------|--------------------------------------------|
| `background`         | `#f8fafc`             | `#0f0f0f`            | Page/app background                        |
| `surface`            | `#ffffff`             | `#27272a`            | Cards, modals, popovers                    |
| `surface-muted`      | `#f1f5f9`             | `#3f3f46`            | Subtle backgrounds (table rows, etc.)      |
| `foreground`         | `#1e293b`             | `#f9fafb`            | Main text color                            |
| `muted`              | `#64748b`             | `#9ca3af`            | Secondary text, placeholders, caption text |
| `border`             | `#e2e8f0`             | `#4a5568`            | Input borders, table cell dividers         |
| `accent-primary`     | `#3b82f6` (indigo-600)| `#60a5fa` (indigo-400)| Primary actions, links, focus rings       |
| `accent-primary-hover`| `#2563eb` (indigo-500)| `#3b82f6`           | Hover states on primary buttons            |
| `accent-primary-active`| `#1d4ed8` (indigo-600)| `#4f46e9`            | Active/pressed state                       |
| `status-critical`    | `#f87171` (red-400)   | `#f87171`            | Critical severity badges/alerts            |
| `status-high`        | `#f97316` (orange-400)| `#f97316`            | High severity                              |
| `status-medium`      | `#eab308` (yellow-400)| `#eab308`            | Medium severity                            |
| `status-low`         | `#22c55e` (green-400)  | `#22c55e`            | Low severity / success                     |
| `link`               | `#3b82f6`             | `#60a5fa`            | Hyperlinks                                 |
| `divider`            | `#cbd5e1`             | `#4a5568`            | Section separators, list dividers          |

**WCAG AA Notes**:
- Contrast ratio foreground-vs-background >= 4.5:1 in dark mode (verified: `#f9fafb` vs `#0f0f0f` = ~14:1, excellent).
- Status colors meet 3:1 minimum on white background, 4.5:1 on dark background when paired with text.
- `accent-primary` focus ring: `4px solid #60a5fa` on dark, `4px solid #2563eb` on light.

### Color Palette CSS (Tailwind config snippet)

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        surface: "var(--surface)",
        "surface-muted": "var(--surface-muted)",
        foreground: "var(--fg)",
        muted: "var(--muted)",
        border: "var(--border)",
        "accent-primary": "var(--accent-primary)",
        "accent-primary-hover": "var(--accent-primary-hover)",
        "accent-primary-active": "var(--accent-primary-active)",
        "status-critical": "var(--status-critical)",
        "status-high": "var(--status-high)",
        "status-medium": "var(--status-medium)",
        "status-low": "var(--status-low)",
        link: "var(--link)",
        divider: "var(--divider)",
      },
    },
  },
};
```

### CSS Variables (globals.css)

```css
:root {
  --bg: #0f0f0f;
  --surface: #27272a;
  --surface-muted: #3f3f46;
  --fg: #f9fafb;
  --muted: #9ca3af;
  --border: #4a5568;
  --accent-primary: #3b82f6;
  --accent-primary-hover: #2563eb;
  --accent-primary-active: #1d4ed8;
  --status-critical: #f87171;
  --status-high: #f97316;
  --status-medium: #eab308;
  --status-low: #22c55e;
  --link: #3b82f6;
  --divider: #4a5568;
}

/* Dark mode prefers-color-scheme override */
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f0f0f;
    --surface: #27272a;
    --surface-muted: #3f3f46;
    --fg: #f9fafb;
    --muted: #9ca3af;
    --border: #4a5568;
    --accent-primary: #60a5fa;
    --accent-primary-hover: #93c5fd;
    --accent-primary-active: #bfdbfe;
    --status-critical: #f87171;
    --status-high: #f97316;
    --status-medium: #eab308;
    --status-low: #22c55e;
    --link: #60a5fa;
    --divider: #4a5568;
  }
}
```

### Usage Guidelines

- **Always pair status colors with a dot + label + icon** (CVD-safe pattern). Never rely on color alone.
- `accent-primary` is the *only* color used for primary CTA buttons, link styling, and focus-visible rings.
- Use `status-low` for success/positive actions; `status-critical` for errors/danger.
- `surface-muted` is used for alternating table row zebra striping, not pure white `#fff`.
- `divider` separates sections without adding visual noise.

---

## 2. Typography — "Inter" as System Font

**Type Scale** (based on `rem` units, `1rem = 16px` by default):

| Token  | Size       | Line Height | Example                    |
|--------|------------|-------------|----------------------------|
| `text.xs` | `0.6875rem` (11px) | `1rem`     | Caption, meta text         |
| `text.sm` | `0.875rem` (14px)   | `1.25rem`  | Small body, metadata       |
| `text.base`| `1rem` (16px)       | `1.5rem`   | Default body copy          |
| `text.lg` | `1.125rem` (18px)   | `1.75rem`  | Large body, section intro  |
| `text.xl` | `1.25rem` (20px)    | `1.75rem`  | Heading 3                  |
| `text[2xl]`| `1.5rem` (24px)     | `2rem`     | Heading 2                  |
| `text[3xl]`| `1.875rem` (30px)   | `2.25rem`  | Heading 1                  |
| `text[4xl]`| `2.25rem` (36px)    | `2.5rem`   | Display (hero)             |

**Font Family**:
- `font-inter` applied to `body` via Tailwind `font-sans` (Inter is a system font on modern OS; falls back to `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`).
- Headings use `font-semibold` to `font-bold` weight.
- Monospaced (`font-mono` / `font-jetbrains-mono`) used exclusively for code blocks, hashes, IP addresses, and table columns where alignment matters.

**Letter Spacing**:
- `tracking-tight` on headings (`-0.025em`).
- `tracking-wide` on uppercase text (nav pills, tags).
- No extra tracking on body copy.

### Tailwind Typography Plugin

```js
// tailwind.config.js
module.exports = {
  plugins: [require("@tailwindcss/typography")],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
    },
  },
};
```

---

## 3. Spacing & Layout

**Spacing Scale** (8-based system, all values in `rem`, derived from `0.25rem = 4px`):

| Token | Value  | Pixel equivalent |
|-------|--------|------------------|
| `0`   | `0`    | `0`              |
| `1`   | `0.25rem` | `4px`          |
| `2`   | `0.5rem`  | `8px`            |
| `3`   | `0.75rem` | `12px`           |
| `4`   | `1rem`    | `16px`           |
| `6`   | `1.5rem`  | `24px`           |
| `8`   | `2rem`    | `32px`           |
| `10`  | `2.5rem`  | `40px`           |
| `12`  | `3rem`    | `48px`           |
| `16`  | `4rem`    | `64px`           |
| `20`  | `5rem`    | `80px`           |
| `24`  | `6rem`    | `96px`           |

**Grid System**:
- Default: `max-w-7xl` centered with `mx-auto`.
- Inside: `grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`.
- Alerts table: `divide-y divide-border` for row separation.
- Sidebar (when desktop): `w-64` fixed, `h-screen` with `flex flex-col`. Mobile: `hidden sm:block`.

**Max Widths**:
- `lg:max-w-7xl` (1440px grid container)
- `xl:max-w-8xl` (1600px for analytics/charts)
- `2xl:max-w-5xl` (for profile/settings pages)

**Data Density** (optional compact mode):
- `data-density="compact"` toggles padding from `p-4` → `p-2`, `gap-6` → `gap-3`, table `text-sm` → `text-xs`.
- Persisted to `localStorage` under key `density-preference`.

---

## 4. Component Specifications (Shadcn UI + Custom Extensions)

All components live under `client/components/`. Shadcn UI components are customized via Tailwind config and CSS variables above. **No custom CSS component overrides its base style without a `var(--...)` token.**

### 4.1 Button

| Variant  | Background          | Color          | Hover                          | Disabled               |
|----------|---------------------|----------------|--------------------------------|------------------------|
| `default`| `var(--accent-primary)` | `white`       | `var(--accent-primary-hover)`  | `opacity-50`           |
| `secondary`| `var(--surface)`   | `var(--muted)` | `hover:bg var(--surface-muted)`| `opacity-50`           |
| `destructive`| `var(--status-critical)` | `white`     | `hover:opacity-90`             | `opacity-50`           |
| `ghost`   | `transparent`       | `var(--muted)` | `hover:bg var(--surface)`      | `opacity-50`           |

- `focus-visible:ring: 2px solid var(--accent-primary)` + `focus-visible:ring-offset: 2px`
- `transition-property: background-color, color, box-shadow; transition-duration: 150ms`
- `min-width: 64px` for consistent hit target; `padding: 0.5rem 1rem` (sm) / `1rem 1.5` (lg)
- Rounded: `rounded-lg` (not sm rounded)

### 4.2 Input & Textarea

| State          | Border                | Focus                          | Invalid                |
|----------------|-----------------------|--------------------------------|------------------------|
| `default`      | `var(--border)`       | —                              | —                      |
| `focus`        | `outline-none`, `ring-2`, `ring var(--accent-primary)` | `border var(--accent-primary)` | —                      |
| `error`        | `ring-2`, `ring-red-500/20` | `border var(--status-critical)` | `ring-offset-2`       |
| `disabled`     | `opacity-40`          | `cursor-not-allowed`           | —                      |

- `rounded-md`, `padding: 0.5rem 0.75rem`, `font-size: 1rem`, `font-sans`
- `resize-y` on textarea (max 4 rows).
- Label styling: `block mb-2 font-medium text-foreground`.

### 4.3 Card

- `bg var(--surface)`, `border var(--border)`, `border-radius lg`
- `shadow-sm` by default; `shadow-md` on hover if `data-hover="true"`.
- `p-6` default padding; `p-4` compact variant.
- Header: `flex items-center justify-between pb-3 border-b border-divider`.
- Footer actions: `flex gap-2 pt-4 border-t border-divider`.

### 4.4 Badge (CVD-Safe: dot + label + icon)

- `display: inline-flex`, `align-items: center`, `gap-1.5`
- `padding: 0.25rem 0.5rem`, `font-size: 0.75rem`, `font-medium`, `border-radius: 9999px`
- **Pattern**: `<span className="w-1 h-1 rounded-full ..." />` + `<span className="...">LABEL</span>` + optional `<Icon>`.
- Variants: `critical`, `high`, `medium`, `low` mapping to status colors.
- `focus-visible` outlines present for keyboard users.

### 4.5 Table

- `min-w-full`, `border-collapse collapse`, `overflow-x-auto` on parent.
- `th, td`: `py-3 px-4 text-left text-sm font-medium text-foreground`, `border border-divider`.
- `thead th`: `bg-transparent`, `text-uppercase text-xs tracking-wider text-muted`.
- Zebra striping: `tbody tr:nth-child(odd) bg var(--surface-muted)`.
- Action columns: `flex items-center gap-2` with icons + tooltips.

### 4.6 Alert Card (Dashboard-specific)

- `card` with `flex flex-col h-full`.
- Top badge: `badge status-<level>` showing severity.
- Title + metadata line (source IP, first seen, last seen).
- Description truncation: `line-clamp-2`.
- Action buttons: `View Details | Add to Case | Trigger SOAR` inline.
- Hover: `shadow-md` lift, `transition-shadow 150ms`.

### 4.7 Skeleton

- Used for all loading states (data tables, card grids, chart containers).
- `bg var(--surface-muted)` with `h-48` (card skeleton) or `h-6` (text skeleton).
- `rounded-lg`, `animate-pulse` (or `animate-shimmer` if preferred).
- Respects `prefers-reduced-motion: reduce` → static gray box (no animation).

### 4.8 Modal (Shadcn Dialog)

- `fixed`, `inset-0`, `z-50`.
- `bg-black/50` backdrop with `backdrop-blur-sm`.
- `max-w-2xl`, `rounded-2xl`, `p-6` to `p-8` content.
- `title` inside header, `Cancel` / `Confirm` actions at bottom.
- **Escape** key closes; click-outside closes.
- Focus returns to triggering element on close.
- `aria-modal="true"`, `role="dialog"` with proper labeling.

### 4.9 Toast (Shadcn Toast)

- `fixed bottom-4 right-4 sm:right-6 md:bottom-6 md:right-8`.
- `max-w-md` with `rounded-lg`, `bg var(--surface)`, `border var(--border)`.
- `p-4`, `font-small`, `text-muted`.
- Action buttons (for confirm toasts): `rounded-full px-3 py-1.5 text-sm`.
- Auto-dismiss after 5s; manual dismiss via "×" button.
- `role="alert"` for accessibility.

### 4.10 Sidebar (Dashboard Layout)

- `w-64 sm:w-auto lg:hidden` (hidden on large screens, i.e., mobile-first).
- `h-screen`, `flex flex-col`, `bg var(--surface)`, `border-r border-divider`.
- Logo top: `h-12 w-12`, `text var(--accent-primary)`.
- Navigation: `nav flex-1 flex flex-col pt-2 gap-4 p-4`.
- Each NavLink: `flex items-center gap-3 px-3 py-2 rounded-md text-sm text-foreground hover:bg var(--surface-muted) active:bg var(--accent-primary)`.
- Active/selected item gets `bg var(--accent-primary)` + `text white`.
- Mobile drawer (overlay): `fixed inset-0 z-40 bg-black/70 backdrop-blur-sm` with slide-in content.

### 4.11 Navbar (Top Bar, on desktop)

- `h-16`, `flex items-center justify-between`, `border-b border-divider`, `bg var(--surface)`, `px-6`.
- Left: `BrandLogo` (SVG, `h-7 w-auto`, `block`).
- Center: `flex items-gap-2` with search input (rounded input, icon button).
- Right: `flex items-center gap-3` with avatar dropdown (avatar initials, notification count badge).

---

## 5. Micro-Interactions (Framer Motion)

All Framer Motion animations respect `prefers-reduced-motion: reduce` → present as instant/snapping changes.

### 5.1 Page Transition (Fade/Slide)

- `<motion.div>` wrapper at root of `layout.tsx`.
- Enter: `transition={{ duration: 0.2, ease: "easeOut" }}`.
- Exit: `transition={{ duration: 0.2, ease: "easeIn", type: "exit" }}`.
- On `prefers-reduced-motion`: `duration: 0` (skip animation).

### 5.2 List Stagger Enter

- `variants` with `staggerChildren: 0.1s`.
- Each `li` / `div` child gets `animate-in` / `fade-in` with `transition={ { delay: index * 0.1 } }`.
- Used for: alert rows, entity list, case timeline, SOAR action history.

### 5.3 Button Haptic Feedback (micro-scale)

- On `whilePress`: `scale: 0.97` + `transition: { duration: 0.08 }`.
- On `whileHover`: `transition: { duration: 150 }` with `opacity` shift of 2%.
- No rotational or large transform movements.

### 5.4 Modal Entrance

- `motion.div` with `initial="closed"`, `animate="open"`.
- `transition: { type: "spring", stiffness: 300, damping: 30 }`.
- backdrop fades in with `opacity-0 → opacity-100` over 150ms.

### 5.5 Toast Appearance

- `motion.div` with `transition: { type: "spring", damping: 20 }`.
- Enter from `bottom-4` → `bottom-4` (short move) + fade `opacity-0 → opacity-100`.
- Exit: fade + slide up + shrink.

---

## 6. Accessibility (a11y) Quick Checks

| Feature                | Implementation                                                  |
|------------------------|-------------------------------------------------------------------|
| Focus-visible          | `focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--accent-primary)]` on all focusable elements |
| ARIA labels            | All interactive cards/buttons have meaningful `aria-label` or inner text |
| Color contrast         | All color combos verified >= 4.5:1 AA (large text >= 3:1)         |
| Keyboard navigation    | Tab order logical; `Escape` closes modals/drawers; `Enter/Space` activates buttons |
| Screen readers       | Tables have `<caption>`; forms have labeled `<label>` elements; live regions (`role="alert"`) for toast/errors |
| Reduced motion         | `prefers-reduced-motion: reduce` strips all Framer Motion animations, falls back to static UI |

---