/**
 * The triage screen's view model — pure, and where the explicit states are decided.
 *
 * design.md §4.3's non-negotiables are rules about *what the screen says*, so they
 * are implemented here rather than inside JSX, where they could only be checked by
 * rendering:
 *
 *   * **A failed explanation renders as `explanation_unavailable` with its reason.**
 *     `explanationView` cannot return an unavailable explanation without a
 *     headline and a reason line, so no component can render R-70's failure as
 *     blank even by accident.
 *   * **An expired evidence window says when it expired.** `evidenceView` computes
 *     the line from the data's own expiry instants — the latest of them, because
 *     that is the moment the last record went — and distinguishes "expired" from
 *     "there was never a trail", which are different claims.
 *   * **The family hint is what earns trust.** `familyHint` reports how many prior
 *     alerts were reviewed as well as how many were false positives: "2 of 2" and
 *     "2 of 200" are different statements and the screen must not make one look
 *     like the other.
 *
 * Everything here is a pure function of the API's answer. Nothing invents a value
 * the API did not send: the design draws contribution weights beside each reason,
 * and this build's payload carries ordered reason strings without them, so the view
 * states that rather than fabricating a bar length.
 */
import { formatInstant, formatStamp } from '../../lib/format';
import type {
  AlertDetail,
  EvidenceOccurrence,
  EvidenceOut,
  ExplanationOut,
  FamilyHistory,
  RelatedAlerts,
  VerdictRecord,
} from './types';
import { verdictLabel } from './verdicts';

/** The order a trail is read in: oldest first, unparseable instants last. */
function atTime(iso: string): number {
  const parsed = Date.parse(iso);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

export function byInstant(a: { at: string }, b: { at: string }): number {
  return atTime(a.at) - atTime(b.at);
}

// --- zone 1: why we flagged this -------------------------------------------

export interface ExplanationView {
  /** True when the model produced no explanation and said so (R-70). */
  unavailable: boolean;
  /** The panel's first line. Never empty: every state has a sentence. */
  headline: string;
  /** The ordered reasons, most contributory first. Empty exactly when unavailable. */
  reasons: string[];
  /** Why it is unavailable, or `null` when it is available. */
  reasonDetail: string | null;
  /** Modalities that scored without contributing reasons, e.g. `['log']`. */
  unavailableModalities: string[];
  /** True while only part of the evidence contributed reasons (§8.1). */
  partialEvidence: boolean;
  /** The line stating that contribution weights are not in this payload. */
  weightsNote: string | null;
}

/**
 * The panel's own statement that the payload carries no weights.
 *
 * design.md §4.3 draws a bar per reason, and T-404's payload — the correlator's
 * `explanation_payload` — carries ordered strings and no contributions. Drawing a
 * bar anyway would be inventing a number, so the panel says what it has.
 */
const WEIGHTS_NOTE =
  'Contribution weights are not carried by this explanation payload; reasons are listed in the order the model ranked them.';

export function explanationView(explanation: ExplanationOut): ExplanationView {
  const reasons = explanation.reasons.filter((reason) => reason.trim() !== '');

  if (explanation.unavailable || reasons.length === 0) {
    return {
      unavailable: true,
      headline: 'explanation_unavailable — the alert was raised without one',
      reasons: [],
      reasonDetail:
        (explanation.detail ?? '').trim() === ''
          ? 'no reason was recorded with this alert'
          : explanation.detail,
      unavailableModalities: explanation.unavailable_modalities,
      partialEvidence: explanation.partial_evidence,
      weightsNote: null,
    };
  }

  return {
    unavailable: false,
    headline:
      reasons.length === 1
        ? '1 contributing signal'
        : `${String(reasons.length)} contributing signals`,
    reasons,
    reasonDetail: null,
    unavailableModalities: explanation.unavailable_modalities,
    partialEvidence: explanation.partial_evidence,
    weightsNote: WEIGHTS_NOTE,
  };
}

// --- zone 2: the timeline ---------------------------------------------------

export interface TimelineTick {
  id: string;
  modality: string;
  at: string;
  /** Where it sits across the span, 0-1. Used for the marker's position. */
  fraction: number;
}

export interface TimelineView {
  /** Start and end of the window read, as design.md §4.3's axis writes them. */
  spanStart: string;
  spanEnd: string;
  spanLabel: string;
  ticks: TimelineTick[];
  /** The first anomalous window — the earliest occurrence the alert kept. */
  firstAnomaly: string | null;
  /** Set when there is nothing to plot, so the panel states it instead of drawing. */
  emptyLine: string | null;
}

/** Where an instant falls across a span, clamped so a marker cannot leave the track. */
export function fractionOf(at: string, start: string, end: string): number {
  const from = Date.parse(start);
  const to = Date.parse(end);
  const point = Date.parse(at);
  if (!Number.isFinite(from) || !Number.isFinite(to) || !Number.isFinite(point)) return 0.5;
  if (to <= from) return 0.5;
  return Math.min(1, Math.max(0, (point - from) / (to - from)));
}

export function timelineView(detail: AlertDetail): TimelineView {
  const { alert } = detail;
  const ticks = [...detail.evidence.occurrences].sort(byInstant).map((occurrence) => ({
    id: occurrence.id,
    modality: occurrence.modality,
    at: occurrence.at,
    fraction: fractionOf(occurrence.at, alert.first_seen, alert.last_seen),
  }));

  return {
    spanStart: alert.first_seen,
    spanEnd: alert.last_seen,
    spanLabel: `${formatInstant(alert.first_seen)} – ${formatInstant(alert.last_seen)}`,
    ticks,
    firstAnomaly: ticks[0]?.at ?? null,
    emptyLine:
      ticks.length === 0
        ? 'No scored window was recorded for this alert, so there is nothing to plot.'
        : null,
  };
}

// --- zone 3: raw evidence ---------------------------------------------------

export interface ModalityCount {
  modality: string;
  count: number;
}

export interface EvidenceView {
  expired: boolean;
  /** `evidence expired at <date>`, or `null` while the records are still there. */
  expiredLine: string | null;
  occurrences: EvidenceOccurrence[];
  counts: ModalityCount[];
  /** Trail entries the read model could not decode, so a short trail is honest. */
  unreadable: number;
  /** Why the trail is incomplete, in the operator's words. */
  note: string | null;
  retentionDays: number;
  grouped: boolean;
  windowLabel: string;
  traceId: string | null;
}

/**
 * The span the alert's evidence actually covers, as design.md §4.3's zone 1 writes
 * it. Falls back to "no window recorded" rather than to the alert's own timestamps:
 * an alert with no scored windows has no evidence window, and showing the case's
 * lifetime under that heading would be a different fact wearing the same label.
 */
export function evidenceWindowLabel(evidence: EvidenceOut): string {
  const times = evidence.occurrences
    .map((occurrence) => Date.parse(occurrence.at))
    .filter((value) => Number.isFinite(value));
  if (times.length === 0) return 'no window recorded';
  const first = formatInstant(new Date(Math.min(...times)).toISOString());
  const last = formatInstant(new Date(Math.max(...times)).toISOString());
  return first === last ? first : `${first} – ${last}`;
}

export function evidenceView(evidence: EvidenceOut): EvidenceView {
  const occurrences = [...evidence.occurrences].sort(byInstant);
  const byModality = new Map<string, number>();
  for (const occurrence of occurrences) {
    byModality.set(occurrence.modality, (byModality.get(occurrence.modality) ?? 0) + 1);
  }

  // The latest expiry, because the first one to pass does not make the evidence
  // gone: the panel's date is the moment the *last* raw record went.
  const expiries = occurrences
    .map((occurrence) => Date.parse(occurrence.expires_at))
    .filter((value) => Number.isFinite(value));
  const expiredAt = expiries.length === 0 ? null : new Date(Math.max(...expiries));

  return {
    expired: evidence.expired,
    expiredLine:
      evidence.expired && expiredAt !== null
        ? `evidence expired at ${formatStamp(expiredAt.toISOString())}`
        : null,
    occurrences,
    counts: [...byModality.entries()]
      .map(([modality, count]) => ({ modality, count }))
      .sort((a, b) => a.modality.localeCompare(b.modality)),
    unreadable: evidence.unreadable,
    note:
      evidence.note === null || evidence.note.trim() === ''
        ? occurrences.length === 0
          ? 'No evidence trail was recorded for this alert.'
          : null
        : evidence.note,
    retentionDays: evidence.retention_days,
    grouped: evidence.grouped,
    windowLabel: evidence.window_id === null ? 'no window recorded' : evidence.window_id,
    traceId: evidence.trace_id,
  };
}

// --- zone 4: context --------------------------------------------------------

export type HintTone = 'warn' | 'neutral';

export interface FamilyHint {
  tone: HintTone;
  /** The sentence, including its counts and window. Never empty. */
  text: string;
}

export function familyHint(history: FamilyHistory): FamilyHint {
  const window = `${String(history.window_days)} d`;

  if (history.prior_alerts === 0) {
    return {
      tone: 'neutral',
      text: `No previous '${history.family}' alerts on this entity in the last ${window}.`,
    };
  }
  if (history.labelled === 0) {
    return {
      tone: 'neutral',
      text: `${String(history.prior_alerts)} prior '${history.family}' alert${
        history.prior_alerts === 1 ? '' : 's'
      } on this entity in ${window}, none reviewed yet.`,
    };
  }
  if (history.false_positive > 0) {
    return {
      tone: 'warn',
      text: `History on this family: analysts marked ${String(
        history.false_positive,
      )} of ${String(history.labelled)} reviewed alerts a false positive in ${window}.`,
    };
  }
  return {
    tone: 'neutral',
    text: `History on this family: ${String(history.labelled)} reviewed in ${window}, none false positive.`,
  };
}

export interface ContextFact {
  label: string;
  value: string;
}

/** The context panel's facts, in the order design.md §4.3 lists them. */
export function contextFacts(detail: AlertDetail): ContextFact[] {
  const { alert, family_history: history, models } = detail;
  return [
    { label: 'Entity', value: `#${String(alert.entity_id)}` },
    { label: 'First seen', value: formatStamp(alert.first_seen) },
    { label: 'Last seen', value: formatStamp(alert.last_seen) },
    { label: 'Occurrences', value: String(alert.occurrence_count) },
    {
      label: `Prior alerts (${String(history.window_days)} d)`,
      value: String(history.prior_alerts),
    },
    {
      label: 'Reviewed',
      value: `${String(history.labelled)} · ${String(history.false_positive)} FP · ${String(
        history.true_positive,
      )} TP · ${String(history.benign)} benign`,
    },
    { label: 'Flow model', value: models.flow ?? 'not recorded' },
    { label: 'Log model', value: models.log ?? 'not recorded' },
  ];
}

// --- the bar, the related list and the queue --------------------------------

export interface VerdictBarFacts {
  severity: string;
  score: string;
  family: string;
  entity: string;
  at: string;
}

export function verdictBarFacts(detail: AlertDetail): VerdictBarFacts {
  const { alert } = detail;
  return {
    severity: alert.severity,
    score: alert.score.toFixed(2),
    family: alert.family,
    entity: `entity #${String(alert.entity_id)}`,
    at: formatInstant(alert.created_at),
  };
}

/** The current verdict as one line, or `null` while the alert is unjudged. */
export function verdictLine(current: VerdictRecord | null): string | null {
  if (current === null) return null;
  return `${verdictLabel(current.verdict)} · ${current.actor} · ${formatInstant(current.at)}`;
}

export interface RelatedView {
  label: string;
  /** True when the API stopped at its limit, so the panel says "showing N of more". */
  truncated: boolean;
  items: RelatedAlerts['items'];
  windowMinutes: number;
}

export function relatedView(related: RelatedAlerts): RelatedView {
  const count = related.items.length;
  return {
    label: count === 1 ? '1 related alert' : `${String(count)} related alerts`,
    truncated: related.truncated,
    items: related.items,
    windowMinutes: related.window_minutes,
  };
}

export interface QueueSummary {
  /** What the list panel says about what it is showing. */
  text: string;
  hasMore: boolean;
}

export function queueSummary(shown: number, hasMore: boolean, windowHours: number): QueueSummary {
  const noun = shown === 1 ? 'alert' : 'alerts';
  if (hasMore) {
    return {
      text: `Showing the newest ${String(shown)} ${noun} of the last ${String(
        windowHours,
      )} h; more are waiting.`,
      hasMore: true,
    };
  }
  return {
    text: `${String(shown)} ${noun} in the last ${String(windowHours)} h.`,
    hasMore: false,
  };
}
