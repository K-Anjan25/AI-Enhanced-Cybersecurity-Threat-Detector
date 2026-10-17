import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { Badge } from './Badge';
import { SEVERITIES } from './severity';

describe('Badge', () => {
  it.each(SEVERITIES)('fills the %s badge with its hue and near-black text', (severity) => {
    // §5.3's rule, as a class assertion: the fill is the base hue and the text is
    // the `onSeverity` token. No variant of this component puts light text on a fill.
    render(<Badge tone={severity}>{severity}</Badge>);

    const badge = screen.getByText(severity);
    expect(badge.className).toContain(`bg-severity-${severity}`);
    expect(badge.className).toContain('text-onSeverity');
    expect(badge).toHaveTextContent(severity);
  });

  it('writes the severity in words and draws no symbol beside it', () => {
    // NFR-09: colour is never the only encoding. The word is the second encoding.
    render(<Badge tone="critical">Critical</Badge>);

    const badge = screen.getByText('Critical');
    expect(badge.textContent).toBe('Critical');
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
