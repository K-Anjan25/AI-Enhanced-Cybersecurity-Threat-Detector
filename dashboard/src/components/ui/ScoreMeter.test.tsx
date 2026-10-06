import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { ScoreMeter, scoreBand } from './ScoreMeter';

describe('ScoreMeter', () => {
  it('exposes the score on the 0\u20131 scale the model uses', () => {
    render(<ScoreMeter label="Lateral movement" score={0.87} threshold={0.62} />);

    const meter = screen.getByRole('meter', { name: 'Lateral movement' });
    expect(meter).toHaveAttribute('aria-valuemin', '0');
    expect(meter).toHaveAttribute('aria-valuemax', '1');
    expect(meter).toHaveAttribute('aria-valuenow', '0.87');
  });

  it('says which side of the threshold the score falls on, in words', () => {
    // The tick alone would be position-only encoding: a screen reader has to hear
    // the comparison, and a reader glancing at the bar has to be able to read it.
    const { unmount } = render(
      <ScoreMeter label="Lateral movement" score={0.87} threshold={0.62} />,
    );
    expect(screen.getByRole('meter')).toHaveAttribute(
      'aria-valuetext',
      '0.87 of 1, at or above the 0.62 threshold',
    );
    unmount();

    render(<ScoreMeter label="Lateral movement" score={0.31} threshold={0.62} />);
    expect(screen.getByRole('meter')).toHaveAttribute(
      'aria-valuetext',
      '0.31 of 1, below the 0.62 threshold',
    );
  });

  it('marks the threshold on the bar, decoratively', () => {
    const { container } = render(
      <ScoreMeter label="Lateral movement" score={0.87} threshold={0.62} />,
    );

    const tick = container.querySelector('[aria-hidden="true"]');
    expect(tick).not.toBeNull();
    expect(tick?.getAttribute('style')).toContain('62%');
  });

  it('omits the tick when no threshold applies', () => {
    const { container } = render(<ScoreMeter label="Lateral movement" score={0.5} />);

    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '0.50 of 1');
  });

  it('clamps a value a hair outside the scale instead of crashing', () => {
    // A pipeline rounding artefact must not take the triage screen down; a bar
    // pinned to its end still tells the truth.
    render(<ScoreMeter label="Lateral movement" score={1.0001} threshold={-0.2} />);

    const meter = screen.getByRole('meter');
    expect(meter).toHaveAttribute('aria-valuenow', '1');
    expect(meter.getAttribute('aria-valuetext')).toContain('the 0.00 threshold');
  });

  it('refuses a score that is not a number', () => {
    expect(() => render(<ScoreMeter label="Lateral movement" score={Number.NaN} />)).toThrow(
      RangeError,
    );
    expect(() =>
      render(<ScoreMeter label="Lateral movement" score={0.5} threshold={Number.NaN} />),
    ).toThrow(RangeError);
  });

  it('agrees with the exported band helper at the boundary', () => {
    // Exactly at the threshold counts as being in the band: the same rule the
    // backend applies when it bands a score.
    expect(scoreBand(0.62, 0.62)).toBe('at-or-above');
    expect(scoreBand(0.6199, 0.62)).toBe('below');
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <div>
        <ScoreMeter label="Above" score={0.9} threshold={0.6} tone="critical" />
        <ScoreMeter label="Below" score={0.1} threshold={0.6} />
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
