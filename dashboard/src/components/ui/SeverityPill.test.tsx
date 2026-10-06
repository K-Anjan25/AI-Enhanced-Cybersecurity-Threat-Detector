import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { SeverityPill } from './SeverityPill';
import { SEVERITIES, SEVERITY_GLYPHS, SEVERITY_LABELS } from './severity';

describe('SeverityPill', () => {
  it.each(SEVERITIES)(
    'labels %s in words, with the glyph and the base hue as its rail',
    (severity) => {
      render(<SeverityPill severity={severity} />);

      const label = screen.getByText(SEVERITY_LABELS[severity]);
      const pill = label.parentElement as HTMLElement;
      // The rail is the base hue (fills and rails, §5.3); the text is the text
      // variant, which §5.3 publishes a ratio for against both backgrounds.
      expect(pill.className).toContain('border-l-rail');
      expect(pill.className).toContain(`border-severity-${severity}`);
      expect(pill.className).toContain(`text-severityText-${severity}`);
    },
  );

  it('hides the glyph it uses as the second encoding', () => {
    render(<SeverityPill severity="medium" />);

    expect(screen.getByText(SEVERITY_GLYPHS.medium)).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders a qualifier in words, so a partial result is never presented as complete', () => {
    // §8.1: "Partial results are labelled, never presented as complete."
    render(<SeverityPill severity="high" detail="partial evidence \u2014 log model unavailable" />);

    expect(screen.getByText(/partial evidence/)).toBeInTheDocument();
  });

  it('has no serious accessibility violations for any severity', async () => {
    const { container } = render(
      <div>
        {SEVERITIES.map((severity) => (
          <SeverityPill key={severity} severity={severity} detail="partial evidence" />
        ))}
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
