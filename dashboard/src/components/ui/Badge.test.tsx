import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { Badge } from './Badge';
import { SEVERITIES } from './severity';

describe('Badge', () => {
  it.each(['critical', 'high'] as const)(
    'fills the %s badge with its hue and ground-coloured text',
    (severity) => {
      // §5.3's rule, as a class assertion: critical and high are the filled shape. The fill
      // is the foreground colour and the text is the `onSeverity` token (the ground colour).
      render(<Badge tone={severity}>{severity}</Badge>);

<<<<<<< HEAD
    const badge = screen.getByText(severity);
    expect(badge.className).toContain(`bg-severity-${severity}`);
    expect(badge.className).toContain('text-onSeverity');
    expect(badge).toHaveTextContent(severity);
  });

  it('says the level in words with no symbol beside it (NFR-09)', () => {
    // The word is the second encoding: colour alone would fail NFR-09, and a
    // decorative mark would only repeat what the label already says. `textContent`
    // is the assertion because a mark anywhere inside the badge lands in it,
    // whether or not it is hidden from assistive technology.
    render(<Badge tone="critical">Critical</Badge>);

    expect(screen.getByText('Critical').textContent).toBe('Critical');
=======
      const badge = screen.getByText(severity);
      expect(badge.className).toContain(`bg-severity-${severity}`);
      expect(badge.className).toContain('text-onSeverity');
      expect(badge).toHaveTextContent(severity);
    },
  );

  it.each(['medium', 'low', 'info', 'benign'] as const)(
    'outlines the %s badge with its word',
    (severity) => {
      // The four lower levels are the outlined shape (D-099): a border in the severity colour
      // and the severity text colour, with no fill. The word is the second encoding.
      render(<Badge tone={severity}>{severity}</Badge>);

      const badge = screen.getByText(severity);
      expect(badge.className).toContain(`border-severity-${severity}`);
      expect(badge.className).toContain(`text-severityText-${severity}`);
      expect(badge.className).not.toContain(`bg-severity-${severity}`);
      expect(badge).toHaveTextContent(severity);
    },
  );

  it('writes the severity in words and draws no symbol beside it', () => {
    // NFR-09: colour is never the only encoding. The word is the second encoding.
    render(<Badge tone="critical">Critical</Badge>);

    const badge = screen.getByText('Critical');
    expect(badge.textContent).toBe('Critical');
>>>>>>> 0f19cb4a572ae9b21e206b1588a6438ef427fc54
  });

  it('renders neutral as a hairline chip rather than a severity fill', () => {
    render(<Badge>42 events</Badge>);

    const badge = screen.getByText('42 events');
    expect(badge.className).toContain('border-line');
    expect(badge.className).not.toContain('bg-severity');
    expect(badge.textContent).toBe('42 events');
  });

  it('has no serious accessibility violations for any tone', async () => {
    const { container } = render(
      <div>
        {SEVERITIES.map((severity) => (
          <Badge key={severity} tone={severity}>
            {severity}
          </Badge>
        ))}
        <Badge>neutral</Badge>
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
