/**
 * The wire shapes of `GET /api/v1/alerts/{alert_id}` (T-404's `AlertDetailOut`).
 *
 * Declared here rather than inferred, and declared field-for-field, because every
 * one of these fields is a rule the screen has to respect:
 *
 *   * `ExplanationOut` is either reasons or `unavailable`, and the two must render
 *     differently — R-70 forbids an empty panel standing in for a failed
 *     explanation, so the screen needs the marker, the `detail` beside it and the
 *     modalities that went missing.
 *   * `EvidenceOut` carries each occurrence's own expiry, so "evidence expired at
 *     <date>" is read off the data rather than computed here from a retention
 *     policy the dashboard cannot see.
 *   * `FamilyHistoryOut` counts only *prior* alerts, which is what makes the hint
 *     a claim about decisions already taken.
 *
 * `AlertRow` comes from `src/api/alerts.ts`: the row shape is shared with the
 * overview, and one definition is what keeps the two screens from disagreeing
 * about what the API returns.
 */
import type { AlertRow } from '../../api/alerts';

/** One recorded verdict (T-309's `VerdictRecordOut`). */
export interface VerdictRecord {
  id: string;
  alert_id: number;
  verdict: string;
  actor: string;
  at: string;
  note: string | null;
  supersedes: string | null;
}

/** What `POST /alerts/{id}/verdict` answers with. */
export interface VerdictOutcome {
  /** `recorded`, or `unchanged` when the same verdict was already current. */
  action: 'recorded' | 'unchanged';
  record: VerdictRecord;
  superseded: VerdictRecord | null;
}

/** R-70's contract: reasons, or the explicit marker and its reason. */
export interface ExplanationOut {
  reasons: string[];
  unavailable: boolean;
  detail: string | null;
  unavailable_modalities: string[];
  partial_evidence: boolean;
  families: string[];
}

export interface EvidenceOccurrence {
  id: string;
  modality: string;
  score: number;
  at: string;
  model: string | null;
  expires_at: string;
  expired: boolean;
}

export interface EvidenceOut {
  window_id: string | null;
  trace_id: string | null;
  grouped: boolean;
  occurrences: EvidenceOccurrence[];
  retention_days: number;
  expired: boolean;
  unreadable: number;
  note: string | null;
}

export interface RelatedAlerts {
  window_minutes: number;
  items: AlertRow[];
  truncated: boolean;
}

export interface FamilyHistory {
  family: string;
  window_days: number;
  prior_alerts: number;
  labelled: number;
  false_positive: number;
  benign: number;
  true_positive: number;
}

export interface AlertModels {
  flow: string | null;
  log: string | null;
}

export interface AlertVerdicts {
  current: VerdictRecord | null;
  history: VerdictRecord[];
}

/** Everything design.md §4.3's four zones render, from one response. */
export interface AlertDetail {
  alert: AlertRow;
  models: AlertModels;
  explanation: ExplanationOut;
  evidence: EvidenceOut;
  verdict: AlertVerdicts;
  related: RelatedAlerts;
  family_history: FamilyHistory;
}
