import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, evidence, occurrence } from '../fixtures';
import { TimelinePanel } from './TimelinePanel';

const SPAN = { first_seen: '2026-03-15T09:55:00Z', last_seen: '2026-03-15T10:00:00Z' };

describe('TimelinePanel', () => {
  it('places each window on the span', () => {
    render(
      <TimelinePanel
        detail={alertDetail({
          alert: { ...alertDetail().alert, ...SPAN },
          evidence: evidence({
            occurrences: [
              occurrence({ id: 'a', at: '2026-03-15T09:58:00Z' }),
              occurrence({ id: 'b', at: '2026-03-15T10:00:00Z' }),
            ],
          }),
        })}
      />,
    );

    // 09:58 is three minutes into a five-minute span.
    expect(screen.getByTestId('tick-a')).toHaveStyle({ left: '60%' });
    expect(screen.getByTestId('tick-b')).toHaveStyle({ left: '100%' });
  });

  it('labels the axis with the instants it runs between', () => {
    render(<TimelinePanel detail={alertDetail({ alert: { ...alertDetail().alert, ...SPAN } })} />);

    // Both ends appear as axis labels.
    expect(screen.getByText('09:55:00Z')).toBeInTheDocument();
    expect(screen.getByText('10:00:00Z')).toBeInTheDocument();
  });

  it('says there is nothing to plot instead of drawing an empty track', () => {
    render(<TimelinePanel detail={alertDetail({ evidence: evidence({ occurrences: [] }) })} />);

    expect(screen.getByRole('status').textContent).toMatch(/nothing to plot/i);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(<TimelinePanel detail={alertDetail()} />);

    await expectAccessible(container);
  });
});
