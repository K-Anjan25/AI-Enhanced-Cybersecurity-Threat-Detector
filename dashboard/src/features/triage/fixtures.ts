/**
 * Test fixtures for the triage screen.
 *
 * A function per wire shape, with overrides, so a test says exactly which part of
 * the answer it is about. They live beside the code rather than in `src/test/`
 * because they are this feature's shapes: a fixture shared across features would
 * make one feature's change break another's tests for no reason.
 *
 * The defaults are a *healthy* alert — reasons, one unexpired flow window, no
 * prior alerts, no verdict — so every test that is about a failure state has to
 * state which failure it means.
 */
import type { AlertRow } from '../../api/alerts';
import type {
  AlertDetail,
  EvidenceOccurrence,
  EvidenceOut,
  ExplanationOut,
  FamilyHistory,
  RelatedAlerts,
  VerdictRecord,
} from './types';

export const AT = '2026-03-15T10:00:00Z';

export function alertRow(overrides: Partial<AlertRow> = {}): AlertRow {
  return {
    id: 42,
    created_at: AT,
    entity_id: 7,
    family: 'Reconnaissance',
    severity: 'critical',
    score: 0.96,
    status: 'open',
    first_seen: '2026-03-15T09:55:00Z',
    last_seen: AT,
    occurrence_count: 1,
    trace_id: 'trace-1',
    ...overrides,
  };
}

export function explanation(overrides: Partial<ExplanationOut> = {}): ExplanationOut {
  return {
    reasons: ['dst_port_count 1,204 vs baseline 12'],
    unavailable: false,
    detail: null,
    unavailable_modalities: [],
    partial_evidence: false,
    families: ['Reconnaissance'],
    ...overrides,
  };
}

export function occurrence(overrides: Partial<EvidenceOccurrence> = {}): EvidenceOccurrence {
  return {
    id: 'win-1',
    modality: 'flow',
    score: 0.96,
    at: AT,
    model: 'flownet@1.4.2',
    expires_at: '2026-04-14T10:00:00Z',
    expired: false,
    ...overrides,
  };
}

export function evidence(overrides: Partial<EvidenceOut> = {}): EvidenceOut {
  return {
    window_id: 'win-1',
    trace_id: 'trace-1',
    grouped: false,
    occurrences: [occurrence()],
    retention_days: 30,
    expired: false,
    unreadable: 0,
    note: null,
    ...overrides,
  };
}

export function verdictRecord(overrides: Partial<VerdictRecord> = {}): VerdictRecord {
  return {
    id: 'v-1',
    alert_id: 42,
    verdict: 'true_positive',
    actor: 'alice@corp',
    at: '2026-03-15T10:03:00Z',
    note: null,
    supersedes: null,
    ...overrides,
  };
}

export function familyHistory(overrides: Partial<FamilyHistory> = {}): FamilyHistory {
  return {
    family: 'Reconnaissance',
    window_days: 30,
    prior_alerts: 0,
    labelled: 0,
    false_positive: 0,
    benign: 0,
    true_positive: 0,
    ...overrides,
  };
}

export function related(overrides: Partial<RelatedAlerts> = {}): RelatedAlerts {
  return { window_minutes: 60, items: [], truncated: false, ...overrides };
}

export function alertDetail(overrides: Partial<AlertDetail> = {}): AlertDetail {
  return {
    alert: alertRow(),
    models: { flow: 'flownet@1.4.2', log: null },
    explanation: explanation(),
    evidence: evidence(),
    verdict: { current: null, history: [] },
    related: related(),
    family_history: familyHistory(),
    ...overrides,
  };
}
