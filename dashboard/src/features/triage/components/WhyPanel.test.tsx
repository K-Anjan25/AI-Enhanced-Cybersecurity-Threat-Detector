/**
 * Zone 1's two states, as rendered.
 *
 * The acceptance criterion is here: an `explanation_unavailable` alert renders the
 * marker *and* the reason it is missing, and an alert with reasons renders them.
 * The test that matters most is the one asserting the marker reaches the screen —
 * a panel that silently rendered nothing would pass every other test in the suite.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, evidence, explanation, occurrence } from '../fixtures';
import { WhyPanel } from './WhyPanel';

describe('WhyPanel', () => {
  it('renders the reasons in the order the model ranked them', () => {
    render(
      <WhyPanel
        detail={alertDetail({
          explanation: explanation({ reasons: ['first reason', 'second reason'] }),
        })}
      />,
    );

    const panel = screen.getByRole('region', { name: 'Why we flagged this' });
    const items = within(panel)
      .getAllByRole('listitem')
      .map((item) => item.textContent);
    expect(items).toEqual(['first reason', 'second reason']);
  });

  it('renders the explanation_unavailable marker with its reason', () => {
    render(
      <WhyPanel
        detail={alertDetail({
          explanation: explanation({
            reasons: [],
            unavailable: true,
            detail: 'occlusion timed out',
            unavailable_modalities: ['log'],
            partial_evidence: true,
          }),
        })}
      />,
    );

    expect(screen.getByText(/explanation_unavailable/)).toBeInTheDocument();
    expect(screen.getByText('occlusion timed out')).toBeInTheDocument();
    expect(screen.getByText(/No reasons from: log\./)).toBeInTheDocument();
    expect(screen.getByText(/partial evidence/)).toBeInTheDocument();
    // Not a blank panel: the state itself is announced, not just styled.
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('states the absence of a reason when the marker carries none', () => {
    render(
      <WhyPanel
        detail={alertDetail({
          explanation: explanation({ reasons: [], unavailable: true, detail: null }),
        })}
      />,
    );

    expect(screen.getByText('no reason was recorded with this alert')).toBeInTheDocument();
  });

  it('says the payload carries no weights rather than drawing one', () => {
    render(<WhyPanel detail={alertDetail()} />);

    expect(screen.getByText(/Contribution weights are not carried/)).toBeInTheDocument();
    // No bar: the design draws one from a number this payload does not carry.
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('names the model and the window the evidence covers', () => {
    render(
      <WhyPanel
        detail={alertDetail({
          models: { flow: 'flownet@1.4.2', log: null },
          evidence: evidence({
            occurrences: [
              occurrence({ id: 'a', at: '2026-03-15T09:58:00Z' }),
              occurrence({ id: 'b', at: '2026-03-15T10:00:00Z' }),
            ],
          }),
        })}
      />,
    );

    expect(screen.getByText(/Model: flownet@1\.4\.2/)).toBeInTheDocument();
    expect(screen.getByText(/09:58:00Z – 10:00:00Z/)).toBeInTheDocument();
  });

  it('says the model version is not recorded rather than showing a blank', () => {
    render(<WhyPanel detail={alertDetail({ models: { flow: null, log: null } })} />);

    expect(screen.getByText(/Model: not recorded/)).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <WhyPanel
        detail={alertDetail({
          explanation: explanation({ unavailable: true, reasons: [], detail: 'x' }),
        })}
      />,
    );

    await expectAccessible(container);
  });
});
