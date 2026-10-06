/**
 * The viewport classes design.md §8.3 publishes, and the media queries that ask for
 * them (T-412).
 *
 * §8.3's table is four rows, so there are four classes and one function that maps a
 * width onto them — the *only* place the numbers 768, 1024 and 1440 are written in
 * the dashboard. `tailwind.config.js` publishes the same three numbers as its
 * `screens`, and `src/theme/tailwind.test.ts` asserts the two agree, so a CSS rule
 * written as `max-md:` and a rule written as `viewport === 'narrow'` cannot come
 * apart and disagree about which side of 768 px a window is on.
 *
 * **The queries are "at most" queries, and that is a decision.** A window that says
 * nothing — a test environment, a browser whose `matchMedia` does not evaluate
 * queries — must come out as the *wide* class rather than the narrow one: hiding
 * screens from an operator we could not measure is a worse failure than showing them
 * the full console, which is also what the product's desktop-first stance implies.
 * With `min-width` queries an unreporting environment fails towards `narrow`, and
 * that is the failure this shape rules out.
 *
 * It lives in `lib` because it is arithmetic and strings: no React, no DOM, and no
 * knowledge of what any screen does with the answer.
 */

/** The three breakpoints of §8.3, in pixels, each one a class's *lower* bound. */
export const VIEWPORT_BREAKPOINTS = {
  /** `compact` starts here: below it, §8.3 offers the triage loop only. */
  compact: 768,
  /** `medium` starts here: single column gives way to §8.3's paired panels. */
  medium: 1024,
  /** `wide` starts here: §8.3's full layout. */
  wide: 1440,
} as const;

/**
 * A window's class, named after §8.3's four rows.
 *
 * `narrow` is §8.3's `< 768 px` row (triage only), `compact` its `768–1023 px` row
 * (single column, drawer nav), `medium` its `1024–1439 px` row (pairs, icon rail) and
 * `wide` its `≥ 1440 px` row (full layout).
 */
export type ViewportClass = 'narrow' | 'compact' | 'medium' | 'wide';

/**
 * The largest width still in the class below `boundary`, as a media query.
 *
 * `0.02` rather than `1`: a CSS pixel is a real number — a 125 % zoom on a 960 px
 * window reports 768 px, and a fractional width reports something between — so the
 * "at most" bound is expressed just under the breakpoint rather than a whole pixel
 * under it. Tailwind's own `max-*` variants take the same position, which is what
 * makes `max-md:` and this query select the same windows.
 */
function atMost(boundary: number): string {
  return `(max-width: ${(boundary - 0.02).toFixed(2)}px)`;
}

/**
 * The three queries the viewport hook listens to.
 *
 * Each is true when the window is at most that class's upper bound, so the three
 * names say *what they include*: `narrowOrCompact` is true for a phone *and* for a
 * tablet, which is exactly what a caller asking "hide the rail?" needs.
 */
export const VIEWPORT_QUERY = {
  /** §8.3's `< 768 px`: the triage-only row. */
  narrow: atMost(VIEWPORT_BREAKPOINTS.compact),
  /** §8.3's `< 1024 px`: the single-column row, phones included. */
  narrowOrCompact: atMost(VIEWPORT_BREAKPOINTS.medium),
  /** §8.3's `< 1440 px`: everything below the full layout. */
  belowWide: atMost(VIEWPORT_BREAKPOINTS.wide),
} as const;

/** What the three queries answered, as the hook reads them. */
export interface ViewportMatches {
  readonly narrow: boolean;
  readonly narrowOrCompact: boolean;
  readonly belowWide: boolean;
}

/**
 * The class a set of query answers describes.
 *
 * The answers are consistent by construction in a real browser (the three queries
 * nest), but the function reads them in order rather than assuming: the narrowest
 * true answer wins, so a browser that answered the first query and not the others
 * still gets a class that is on the narrow side of the disagreement.
 */
export function viewportClassFrom(matches: ViewportMatches): ViewportClass {
  if (matches.narrow) return 'narrow';
  if (matches.narrowOrCompact) return 'compact';
  if (matches.belowWide) return 'medium';
  return 'wide';
}

/**
 * The class a window *width* describes — the same mapping `viewportClassFrom` makes
 * from query answers, written out so the two can be checked against each other (see
 * `viewport.test.ts`, which sweeps every width across the three boundaries).
 */
export function viewportClassOf(width: number): ViewportClass {
  if (!Number.isFinite(width) || width < 0) {
    throw new RangeError(`viewport width must be a non-negative number, got ${String(width)}`);
  }
  if (width < VIEWPORT_BREAKPOINTS.compact) return 'narrow';
  if (width < VIEWPORT_BREAKPOINTS.medium) return 'compact';
  if (width < VIEWPORT_BREAKPOINTS.wide) return 'medium';
  return 'wide';
}
