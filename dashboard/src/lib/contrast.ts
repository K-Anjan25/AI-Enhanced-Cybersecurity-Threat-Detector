/**
 * WCAG 2.1 contrast utilities.
 *
 * design.md publishes specific contrast ratios for every text token. Those
 * numbers are only trustworthy if they are recomputed, so tokens.test.ts uses
 * this module against the real values in src/index.css.
 */

/** Parse `#rgb` or `#rrggbb` into linear-light-precision sRGB channels. */
export function hexToRgb(hex: string): [number, number, number] {
  const value = hex.trim().replace(/^#/, '');
  const expanded =
    value.length === 3
      ? value
          .split('')
          .map((c) => c + c)
          .join('')
      : value;
  if (!/^[0-9a-fA-F]{6}$/.test(expanded)) {
    throw new Error(`Not a hex colour: ${hex}`);
  }
  return [
    parseInt(expanded.slice(0, 2), 16) / 255,
    parseInt(expanded.slice(2, 4), 16) / 255,
    parseInt(expanded.slice(4, 6), 16) / 255,
  ];
}

/** sRGB channel → linear light, per the WCAG relative-luminance definition. */
function linearise(channel: number): number {
  return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
}

/** Relative luminance in [0, 1]. */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * linearise(r) + 0.7152 * linearise(g) + 0.0722 * linearise(b);
}

/**
 * Contrast ratio between two colours, in the range 1:1 to 21:1.
 * Order of arguments does not matter.
 */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

/** WCAG AA minimum for normal-size text. */
export const AA_NORMAL_TEXT = 4.5;
/** WCAG AA minimum for large text and for non-text UI components. */
export const AA_LARGE_AND_UI = 3;
