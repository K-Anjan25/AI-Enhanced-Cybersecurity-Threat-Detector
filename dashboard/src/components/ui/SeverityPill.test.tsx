import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { SeverityPill } from './SeverityPill';
import { SEVERITIES, SEVERITY_LABELS } from './severity';

describe('SeverityPill', () => {
  it.each(SEVERITIES)('labels %s in words, with the base hue as its rail', (severity) => {
    render(<SeverityPill severity={severity} />);

    const label = screen.getByText(SEVERITY_LABELS[severity]);
    const pill = label.parentElement as HTMLElement;
    // The rail is the base hue (fills and rails, §5.3); the text is the text
    // variant, which §5.3 publishes a ratio for against both backgrounds.
    expect(pill.className).toContain('border-l-rail');
    expect(pill.className).toContain(`border-severity-${severity}`);
    expect(pill.className).toContain(`text-severityText-${severity}`);
  });

<<<<<<< HEAD
  it('shows the level as its word and nothing beside it', () => {
    // The word is the whole second encoding (NFR-09) — no decorative mark
    // repeats what the label already says.
=======
  it('draws no symbol, so the word carries the severity', () => {
>>>>>>> 0f19cb4a572ae9b21e206b1588a6438ef427fc54
    render(<SeverityPill severity="medium" />);

    const pill = screen.getByText(SEVERITY_LABELS.medium).parentElement as HTMLElement;
    expect(pill.textContent).toBe(SEVERITY_LABELS.medium);
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
