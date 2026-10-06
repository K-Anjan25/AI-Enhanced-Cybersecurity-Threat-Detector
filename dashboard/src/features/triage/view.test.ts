/**
 * The view model's rules, asserted without rendering.
 *
 * These are design.md §4.3's non-negotiables in their purest form: what each state
 * *says*. The rendering tests above this one check that the sentences reach the
 * screen; these check that they are the right sentences — and, in the two cases
 * that matter most, that the wrong state cannot be produced at all.
 */
import { describe, expect, it } from 'vitest';

import { alertDetail, evidence, explanation, familyHistory, occurrence, related } from './fixtures';
import {
  contextFacts,
  evidenceView,
  evidenceWindowLabel,
  explanationView,
  familyHint,
  fractionOf,
  queueSummary,
  relatedView,
  timelineView,
  verdictBarFacts,
  verdictLine,
} from './view';

describe('explanationView', () => {
  it('renders the reasons when the model produced them', () => {
    const view = explanationView(explanation({ reasons: ['a', 'b'] }));

    expect(view.unavailable).toBe(false);
    expect(view.reasons).toEqual(['a', 'b']);
    expect(view.headline).toBe('2 contributing signals');
  });

  it('cannot render an unavailable explanation without a sentence and a reason', () => {
    // R-70's failure mode is a blank panel; the view has no shape for one.
    const view = explanationView(
      explanation({ reasons: [], unavailable: true, detail: 'occlusion timed out' }),
    );

    expect(view.unavailable).toBe(true);
    expect(view.headline).toContain('explanation_unavailable');
    expect(view.reasonDetail).toBe('occlusion timed out');
    expect(view.reasons).toEqual([]);
  });

  it('states the missing reason when the marker carries none', () => {
    const view = explanationView(explanation({ reasons: [], unavailable: true, detail: null }));

    expect(view.reasonDetail).toBe('no reason was recorded with this alert');
    expect((view.reasonDetail ?? '').trim()).not.toBe('');
  });

  it('treats an empty reason list as unavailable even if the flag says otherwise', () => {
    // A payload that claims success and carries nothing is the blank panel R-70
    // forbids; the flag is not allowed to override what the data shows.
    const view = explanationView(explanation({ reasons: ['', '  '], unavailable: false }));

    expect(view.unavailable).toBe(true);
    expect(view.headline).toContain('explanation_unavailable');
  });

  it('keeps the reasons and names the modality that went missing', () => {
    const view = explanationView(
      explanation({
        reasons: ['flow_duration 0.02s vs baseline 1.8s'],
        partial_evidence: true,
        unavailable_modalities: ['log'],
      }),
    );

    expect(view.unavailable).toBe(false);
    expect(view.reasons).toHaveLength(1);
    expect(view.partialEvidence).toBe(true);
    expect(view.unavailableModalities).toEqual(['log']);
  });

  it('says that the payload carries no contribution weights', () => {
    // design.md draws a bar per reason; this payload has no number to draw from,
    // and inventing one is the one thing the panel must not do.
    const view = explanationView(explanation());

    expect(view.weightsNote).not.toBeNull();
    expect(view.weightsNote).toMatch(/weights/i);
  });
});

describe('evidenceView', () => {
  it('says when the evidence expired', () => {
    const view = evidenceView(
      evidence({
        expired: true,
        occurrences: [occurrence({ expired: true, expires_at: '2026-04-14T10:00:00Z' })],
      }),
    );

    expect(view.expiredLine).toBe('evidence expired at 14 Apr 2026, 10:00:00Z');
  });

  it('dates the expiry at the last record to go, not the first', () => {
    const view = evidenceView(
      evidence({
        expired: true,
        occurrences: [
          occurrence({ id: 'a', expired: true, expires_at: '2026-04-14T10:00:00Z' }),
          occurrence({ id: 'b', expired: true, expires_at: '2026-04-20T10:00:00Z' }),
        ],
      }),
    );

    expect(view.expiredLine).toBe('evidence expired at 20 Apr 2026, 10:00:00Z');
  });

  it('does not say "expired" when some of the trail is still there', () => {
    const view = evidenceView(
      evidence({
        expired: false,
        occurrences: [occurrence({ id: 'a', expired: true }), occurrence({ id: 'b' })],
      }),
    );

    expect(view.expiredLine).toBeNull();
    expect(view.occurrences.map((entry) => entry.expired)).toEqual([true, false]);
  });

  it('orders the trail oldest first, whatever order it arrived in', () => {
    const view = evidenceView(
      evidence({
        occurrences: [
          occurrence({ id: 'late', at: '2026-03-15T10:00:00Z' }),
          occurrence({ id: 'early', at: '2026-03-15T09:00:00Z' }),
        ],
      }),
    );

    expect(view.occurrences.map((entry) => entry.id)).toEqual(['early', 'late']);
  });

  it('counts the trail per modality, so the tabs can be labelled', () => {
    const view = evidenceView(
      evidence({
        occurrences: [
          occurrence({ id: 'a', modality: 'flow' }),
          occurrence({ id: 'b', modality: 'flow' }),
          occurrence({ id: 'c', modality: 'log' }),
        ],
      }),
    );

    expect(view.counts).toEqual([
      { modality: 'flow', count: 2 },
      { modality: 'log', count: 1 },
    ]);
  });

  it('states a missing trail rather than leaving the panel empty', () => {
    const view = evidenceView(evidence({ occurrences: [], note: null }));

    expect(view.note).toBe('No evidence trail was recorded for this alert.');
  });

  it('reports unreadable entries so a short trail is not read as a complete one', () => {
    const view = evidenceView(evidence({ unreadable: 2 }));

    expect(view.unreadable).toBe(2);
  });

  it('labels the evidence window from the windows themselves', () => {
    const label = evidenceWindowLabel(
      evidence({
        occurrences: [
          occurrence({ id: 'a', at: '2026-03-15T09:58:00Z' }),
          occurrence({ id: 'b', at: '2026-03-15T10:00:00Z' }),
        ],
      }),
    );

    expect(label).toBe('09:58:00Z – 10:00:00Z');
  });

  it("says a window is missing rather than borrowing the alert's own timestamps", () => {
    expect(evidenceWindowLabel(evidence({ occurrences: [] }))).toBe('no window recorded');
  });
});

describe('timelineView', () => {
  it('places each window across the span and names the first one', () => {
    const view = timelineView(
      alertDetail({
        evidence: evidence({
          occurrences: [
            occurrence({ id: 'a', at: '2026-03-15T09:58:00Z' }),
            occurrence({ id: 'b', at: '2026-03-15T10:00:00Z' }),
          ],
        }),
      }),
    );

    expect(view.ticks.map((tick) => tick.id)).toEqual(['a', 'b']);
    expect(view.firstAnomaly).toBe('2026-03-15T09:58:00Z');
    expect(view.ticks[0]?.fraction).toBeCloseTo(0.6, 5);
    expect(view.ticks[1]?.fraction).toBeCloseTo(1, 5);
  });

  it('says there is nothing to plot rather than drawing an empty track', () => {
    const view = timelineView(alertDetail({ evidence: evidence({ occurrences: [] }) }));

    expect(view.ticks).toEqual([]);
    expect(view.emptyLine).toMatch(/nothing to plot/i);
  });

  it('clamps a marker to the track when an instant falls outside the span', () => {
    expect(fractionOf('2026-03-15T11:00:00Z', '2026-03-15T09:00:00Z', '2026-03-15T10:00:00Z')).toBe(
      1,
    );
    expect(fractionOf('2026-03-15T08:00:00Z', '2026-03-15T09:00:00Z', '2026-03-15T10:00:00Z')).toBe(
      0,
    );
  });

  it('centres a marker when the span has no width or a bad instant', () => {
    expect(fractionOf('2026-03-15T10:00:00Z', '2026-03-15T10:00:00Z', '2026-03-15T10:00:00Z')).toBe(
      0.5,
    );
    expect(fractionOf('nonsense', '2026-03-15T09:00:00Z', '2026-03-15T10:00:00Z')).toBe(0.5);
  });
});

describe('familyHint', () => {
  it('says plainly when there is no history', () => {
    const hint = familyHint(familyHistory());

    expect(hint.tone).toBe('neutral');
    expect(hint.text).toContain('No previous');
    expect(hint.text).toContain('30 d');
  });

  it('warns when analysts have called this family a false positive here', () => {
    // The hint exists to tell the analyst the model has been wrong here before.
    const hint = familyHint(familyHistory({ prior_alerts: 3, labelled: 3, false_positive: 2 }));

    expect(hint.tone).toBe('warn');
    expect(hint.text).toContain('2 of 3');
    expect(hint.text).toContain('false positive');
  });

  it('separates "nobody looked" from "everybody agreed"', () => {
    const unreviewed = familyHint(familyHistory({ prior_alerts: 5, labelled: 0 }));
    const agreed = familyHint(familyHistory({ prior_alerts: 5, labelled: 5, true_positive: 5 }));

    expect(unreviewed.tone).toBe('neutral');
    expect(unreviewed.text).toContain('none reviewed yet');
    expect(agreed.tone).toBe('neutral');
    expect(agreed.text).toContain('none false positive');
  });

  it('says "1 prior alert" rather than "1 prior alerts"', () => {
    expect(familyHint(familyHistory({ prior_alerts: 1 })).text).toContain('1 prior');
    expect(familyHint(familyHistory({ prior_alerts: 1 })).text).toContain('alert ');
    expect(familyHint(familyHistory({ prior_alerts: 2 })).text).toContain('alerts');
  });
});

describe('contextFacts', () => {
  it('carries the counts a reader can check the hint against', () => {
    const facts = contextFacts(
      alertDetail({
        family_history: familyHistory({
          prior_alerts: 3,
          labelled: 3,
          false_positive: 2,
          true_positive: 1,
        }),
      }),
    );
    const reviewed = facts.find((fact) => fact.label === 'Reviewed');

    expect(reviewed?.value).toBe('3 · 2 FP · 1 TP · 0 benign');
    expect(facts.find((fact) => fact.label.endsWith('(30 d)'))?.value).toBe('3');
  });

  it('says a model version is not recorded instead of leaving a gap', () => {
    const facts = contextFacts(alertDetail({ models: { flow: null, log: null } }));

    expect(facts.filter((fact) => fact.value === 'not recorded')).toHaveLength(2);
  });
});

describe('the bar and the queue', () => {
  it('prints the score to two places and the instant in UTC', () => {
    const facts = verdictBarFacts(alertDetail());

    expect(facts.score).toBe('0.96');
    expect(facts.at).toBe('10:00:00Z');
    expect(facts.severity).toBe('critical');
  });

  it('has no verdict line until a verdict exists', () => {
    expect(verdictLine(null)).toBeNull();
    expect(
      verdictLine({
        id: 'v',
        alert_id: 42,
        verdict: 'false_positive',
        actor: 'alice@corp',
        at: '2026-03-15T10:03:00Z',
        note: null,
        supersedes: null,
      }),
    ).toBe('False positive · alice@corp · 10:03:00Z');
  });

  it('says "more are waiting" rather than presenting a page as the queue', () => {
    expect(queueSummary(100, true, 24).text).toContain('more are waiting');
    expect(queueSummary(3, false, 24).text).toBe('3 alerts in the last 24 h.');
    expect(queueSummary(1, false, 24).text).toBe('1 alert in the last 24 h.');
  });

  it('labels related alerts and passes the truncation through', () => {
    const view = relatedView(related({ items: [], truncated: true }));

    expect(view.label).toBe('0 related alerts');
    expect(view.truncated).toBe(true);
    expect(view.windowMinutes).toBe(60);
  });
});
