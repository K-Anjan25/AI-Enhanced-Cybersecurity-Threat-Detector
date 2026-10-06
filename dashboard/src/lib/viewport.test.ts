/**
 * §8.3's breakpoints and the two mappings onto them (T-412).
 *
 * The suite's real claim is the agreement between the two ways of asking the same
 * question: `viewportClassFrom` reads three media-query answers and `viewportClassOf`
 * reads a width, and the sweep asserts they pick the same class for every width. Those
 * two functions are what a screen and a stylesheet respectively act on, so a
 * disagreement between them would be a `max-md:hidden` panel rendered beside a page
 * that thinks it is on a desktop.
 */
import { describe, expect, it } from 'vitest';

import {
  VIEWPORT_BREAKPOINTS,
  VIEWPORT_QUERY,
  viewportClassFrom,
  viewportClassOf,
  type ViewportClass,
  type ViewportMatches,
} from './viewport';

/** What a browser would answer for these three queries at this width. */
function matchesAt(width: number): ViewportMatches {
  const boundOf = (query: string): number =>
    Number.parseFloat(/\(max-width:\s*([\d.]+)px\)/.exec(query)![1]!);
  return {
    narrow: width <= boundOf(VIEWPORT_QUERY.narrow),
    narrowOrCompact: width <= boundOf(VIEWPORT_QUERY.narrowOrCompact),
    belowWide: width <= boundOf(VIEWPORT_QUERY.belowWide),
  };
}

describe('the published breakpoints', () => {
  it('names design.md §8.3’s three numbers', () => {
    expect(VIEWPORT_BREAKPOINTS).toEqual({ compact: 768, medium: 1024, wide: 1440 });
  });

  it('asks for the class below each boundary, never across it', () => {
    // The *last* width in the class below, which is why the bound is a hair under the
    // breakpoint: `max-width: 768px` would put a 768 px window in the narrow class and
    // contradict `viewportClassOf`.
    expect(VIEWPORT_QUERY.narrow).toBe('(max-width: 767.98px)');
    expect(VIEWPORT_QUERY.narrowOrCompact).toBe('(max-width: 1023.98px)');
    expect(VIEWPORT_QUERY.belowWide).toBe('(max-width: 1439.98px)');
  });

  it('queries in the "at most" direction, so an unmeasurable window is not treated as narrow', () => {
    // A `min-width` query would fail this: with no environment to answer it, every
    // `matches` would be false and the app would take the narrow branch — hiding most
    // of the console from an operator it could not measure.
    for (const query of Object.values(VIEWPORT_QUERY)) {
      expect(query).toContain('max-width');
      expect(query).not.toContain('min-width');
    }
  });
});

describe('the class a window is in', () => {
  it('agrees with the media queries at every width', () => {
    // The sweep is what makes the claim rather than four spot checks: 0 … 2000 px is
    // every window this app will meet, and both functions have to pick the same class
    // at each one. The sliver between a query's bound (767.98) and its breakpoint
    // (768) is the one place the two differ, and it is unreachable in whole pixels —
    // which is the whole point of choosing 0.02 over 1: a fractional width at the
    // boundary rounds into the class its neighbours are in.
    for (let width = 0; width <= 2000; width += 1) {
      expect(viewportClassFrom(matchesAt(width)), `width ${String(width)}`).toBe(
        viewportClassOf(width),
      );
    }
  });

  it('maps each boundary to the documented side', () => {
    const expected: [number, ViewportClass][] = [
      [320, 'narrow'],
      [767, 'narrow'],
      [768, 'compact'],
      [900, 'compact'],
      [1023, 'compact'],
      [1024, 'medium'],
      [1200, 'medium'],
      [1439, 'medium'],
      [1440, 'wide'],
      [2560, 'wide'],
    ];
    for (const [width, cls] of expected) {
      expect(viewportClassOf(width), `${String(width)} px`).toBe(cls);
      expect(viewportClassFrom(matchesAt(width)), `${String(width)} px`).toBe(cls);
    }
  });

  it('refuses a width that is not a measurement', () => {
    expect(() => viewportClassOf(Number.NaN)).toThrow(RangeError);
    expect(() => viewportClassOf(-1)).toThrow(RangeError);
  });

  it('believes the narrowest answer when the three disagree', () => {
    // A browser cannot produce this (the queries nest), which is exactly why the
    // function has to have an opinion: the narrowest true answer is the safe one, since
    // it is the one that keeps a screen the operator cannot use off the window.
    expect(viewportClassFrom({ narrow: true, narrowOrCompact: false, belowWide: false })).toBe(
      'narrow',
    );
    expect(viewportClassFrom({ narrow: false, narrowOrCompact: true, belowWide: false })).toBe(
      'compact',
    );
    expect(viewportClassFrom({ narrow: false, narrowOrCompact: false, belowWide: true })).toBe(
      'medium',
    );
    expect(viewportClassFrom({ narrow: false, narrowOrCompact: false, belowWide: false })).toBe(
      'wide',
    );
  });
});
