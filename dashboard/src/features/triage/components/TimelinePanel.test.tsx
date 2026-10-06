import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, evidence, occurrence } from '../fixtures';
import { TimelinePanel } from './TimelinePanel';

const SPAN = { first_seen: '2026-03-15T09:55:00Z', last_seen: '2026-03-15T10:00:00Z' };

describe('TimelinePanel', () => {
  it('places each window on the span and names the first anomalous one', () => {
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
    expect(screen.getByText(/first anomalous window/)).toBeInTheDocument();
    expect(screen.getByText('09:58:00Z')).toBeInTheDocument();
  });

  it('labels the axis with the instants it runs between', () => {
    render(<TimelinePanel detail={alertDetail({ alert: { ...alertDetail().alert, ...SPAN } })} />);

    // Both ends appear: the start only as an axis label, the end also as the
    // window that arrived at it, so this counts rather than getting one node.
    expect(screen.getByText('09:55:00Z')).toBeInTheDocument();
    expect(screen.getAllByText('10:00:00Z').length).toBeGreaterThanOrEqual(2);
  });

  it('says there is nothing to plot instead of drawing an empty track', () => {
    render(<TimelinePanel detail={alertDetail({ evidence: evidence({ occurrences: [] }) })} />);

    expect(screen.getByRole('status').textContent).toMatch(/nothing to plot/i);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('names the chart primitives it is not, rather than imitating them', () => {
    render(<TimelinePanel detail={alertDetail()} />);

    expect(screen.getByText(/arrive with the T-406 chart primitives/)).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(<TimelinePanel detail={alertDetail()} />);

    await expectAccessible(container);
  });
});
