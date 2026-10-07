/**
 * Zone 4: the facts, the trust hint and the verdict history.
 *
 * The hint is the reason this panel exists — "it tells the analyst the model has
 * been wrong here before" — so the assertions are on the sentence and the counts
 * behind it, and on the case where the hint must *not* warn.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, familyHistory, verdictRecord } from '../fixtures';
import { ContextPanel } from './ContextPanel';

describe('ContextPanel', () => {
  it('carries the counts the hint is derived from', () => {
    render(
      <ContextPanel
        detail={alertDetail({
          family_history: familyHistory({
            prior_alerts: 3,
            labelled: 3,
            false_positive: 2,
            true_positive: 1,
          }),
        })}
      />,
    );

    expect(screen.getByText('Entity')).toBeInTheDocument();
    expect(screen.getByText('#7')).toBeInTheDocument();
    expect(screen.getByText('Prior alerts (30 d)')).toBeInTheDocument();
    expect(screen.getByText('3 · 2 FP · 1 TP · 0 benign')).toBeInTheDocument();
  });

  it('warns when the model has been wrong on this family before', () => {
    render(
      <ContextPanel
        detail={alertDetail({
          family_history: familyHistory({ prior_alerts: 3, labelled: 3, false_positive: 2 }),
        })}
      />,
    );

    const hint = screen.getByRole('status');
    expect(hint.textContent).toContain('2 of 3');
    expect(hint.textContent).toContain('false positive');
    // The mark that goes with the warning is drawn (Lucide, §5.6) rather than typed:
    // it used to be the character `\u26A0`, which this assertion pinned — a check on
    // a text glyph cannot tell a triangle from a tofu box. It is `aria-hidden` (the
    // sentence is the message), so it has no role to query it by; this is this file's
    // exemption in `src/test/query-rule.test.ts`, beside the role query above.
    expect(hint.querySelector('svg')).not.toBeNull();
  });

  it('does not warn when the history is empty or agreed with', () => {
    const { unmount } = render(<ContextPanel detail={alertDetail()} />);
    expect(screen.getByRole('status').textContent).toContain('No previous');
    // No warning, no mark: the panel does not decorate a calm history with one.
    expect(screen.getByRole('status').querySelector('svg')).toBeNull();
    unmount();

    render(
      <ContextPanel
        detail={alertDetail({
          family_history: familyHistory({ prior_alerts: 4, labelled: 4, true_positive: 4 }),
        })}
      />,
    );

    const hint = screen.getByRole('status');
    expect(hint.textContent).toContain('none false positive');
    expect(hint.textContent).not.toContain('\u26A0');
  });

  it('says nobody has reviewed the prior alerts when nobody has', () => {
    render(
      <ContextPanel
        detail={alertDetail({ family_history: familyHistory({ prior_alerts: 5, labelled: 0 }) })}
      />,
    );

    expect(screen.getByRole('status').textContent).toContain('none reviewed yet');
  });

  it('lists the verdict history with who wrote it and what it superseded', () => {
    render(
      <ContextPanel
        detail={alertDetail({
          verdict: {
            current: verdictRecord({ verdict: 'benign' }),
            history: [
              verdictRecord({ id: 'v-1', verdict: 'true_positive' }),
              verdictRecord({ id: 'v-2', verdict: 'benign', supersedes: 'v-1' }),
            ],
          },
        })}
      />,
    );

    expect(screen.getByText(/True positive · alice@corp/)).toBeInTheDocument();
    expect(screen.getByText(/\(supersedes v-1\)/)).toBeInTheDocument();
  });

  it('says no verdict has been recorded yet when the history is empty', () => {
    render(<ContextPanel detail={alertDetail()} />);

    expect(screen.getByText('No verdict has been recorded on this alert.')).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <ContextPanel
        detail={alertDetail({
          family_history: familyHistory({ prior_alerts: 3, labelled: 3, false_positive: 2 }),
          verdict: { current: verdictRecord(), history: [verdictRecord()] },
        })}
      />,
    );

    await expectAccessible(container);
  });
});
