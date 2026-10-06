/**
 * Reading the token layer, asserted in a document rather than argued about.
 *
 * The overview's `charts.test.ts` is a node-environment suite, so `window` does not
 * exist there and `readPalette` returns through its first branch — the branch that
 * actually reads a stylesheet has no test at all. This suite is that test: it runs in
 * jsdom, declares the variables the way `index.css` does, and checks both directions
 * (declared, and undeclared).
 */
import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { CHART_VARIABLES, SEVERITY_VARIABLES, readPalette, useChartPalette } from './palette';

const DECLARED: Record<string, string> = {
  [SEVERITY_VARIABLES.critical]: 'rgb(220, 38, 38)',
  [SEVERITY_VARIABLES.high]: 'rgb(234, 88, 12)',
  [SEVERITY_VARIABLES.medium]: 'rgb(202, 138, 4)',
  [SEVERITY_VARIABLES.low]: 'rgb(37, 99, 235)',
  [SEVERITY_VARIABLES.info]: 'rgb(100, 116, 139)',
  [SEVERITY_VARIABLES.benign]: 'rgb(5, 150, 105)',
  [CHART_VARIABLES.text]: 'rgb(71, 85, 105)',
  [CHART_VARIABLES.grid]: 'rgb(226, 232, 240)',
};

function declare(variables: Record<string, string>): void {
  for (const [name, value] of Object.entries(variables)) {
    document.documentElement.style.setProperty(name, value);
  }
}

function clear(): void {
  for (const name of Object.keys(DECLARED)) {
    document.documentElement.style.removeProperty(name);
  }
}

afterEach(() => {
  clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('readPalette', () => {
  it('returns no colour at all when the document declares none', () => {
    // Not a fallback hue: an invented colour here would be a chart that looks
    // deliberate while telling the reader nothing about which token it used.
    const palette = readPalette();

    expect(palette.critical).toBe('transparent');
    expect(palette.benign).toBe('transparent');
    expect(palette.muted).toBe('transparent');
    expect(palette.grid).toBe('transparent');
  });

  it('returns the document’s own value for each token', () => {
    declare(DECLARED);

    const palette = readPalette();

    expect(palette.critical).toBe('rgb(220, 38, 38)');
    expect(palette.benign).toBe('rgb(5, 150, 105)');
    expect(palette.muted).toBe('rgb(71, 85, 105)');
    expect(palette.grid).toBe('rgb(226, 232, 240)');
  });

  it('trims the declaration, because a stylesheet may pad it', () => {
    declare({ [SEVERITY_VARIABLES.high]: '   rgb(234, 88, 12)   ' });

    expect(readPalette().high).toBe('rgb(234, 88, 12)');
  });

  it('reads every severity, not only the ones a single panel happens to use', () => {
    declare(DECLARED);

    const palette = readPalette();

    for (const name of Object.keys(SEVERITY_VARIABLES)) {
      expect(palette[name as keyof typeof SEVERITY_VARIABLES]).toBe(
        DECLARED[SEVERITY_VARIABLES[name as keyof typeof SEVERITY_VARIABLES]],
      );
    }
  });
});

/** A panel that shows the hue it currently believes in. */
function Panel(): JSX.Element {
  const palette = useChartPalette();
  return <p>critical is {palette.critical}</p>;
}

describe('useChartPalette', () => {
  it('follows the theme when someone else changes it', async () => {
    // `ThemeProvider` writes `data-theme` in a passive effect, children-first, so a
    // chart that re-read on its own render would be one paint behind. The hook watches
    // the attribute instead — and this asserts that, whoever set it.
    declare({ [SEVERITY_VARIABLES.critical]: 'rgb(220, 38, 38)' });
    render(<Panel />);
    expect(screen.getByText('critical is rgb(220, 38, 38)')).toBeInTheDocument();

    declare({ [SEVERITY_VARIABLES.critical]: 'rgb(251, 146, 60)' });
    act(() => {
      document.documentElement.setAttribute('data-theme', 'light');
    });

    expect(await screen.findByText('critical is rgb(251, 146, 60)')).toBeInTheDocument();
  });

  it('shows the document as it is at mount, with no effect needed first', () => {
    declare({ [SEVERITY_VARIABLES.critical]: 'rgb(220, 38, 38)' });

    render(<Panel />);

    // The initial state is the read, not a placeholder: a chart that painted one
    // frame of `transparent` before its effect ran would flicker on every mount.
    expect(screen.getByText('critical is rgb(220, 38, 38)')).toBeInTheDocument();
  });
});

describe('the read is not cached', () => {
  it('reflects a declaration made after an earlier read', () => {
    expect(readPalette().grid).toBe('transparent');

    declare({ [CHART_VARIABLES.grid]: 'rgb(226, 232, 240)' });

    expect(readPalette().grid).toBe('rgb(226, 232, 240)');
  });
});
