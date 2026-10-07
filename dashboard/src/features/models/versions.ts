/**
 * The model ops screens' derived model: what a version table shows, what a metric
 * card is allowed to say, and when a promotion may be submitted (T-409, FR-30…FR-33).
 *
 * Everything here is pure, because the rules are the part worth testing: a component
 * that decided for itself whether a promotion was ready, or printed a metric value
 * without its run, would be a second place for those rules to live.
 *
 * Four decisions are encoded rather than left to a component:
 *
 *   * **A number never travels without its run (R-74).** Every metric card carries
 *     the artifact and the field the value was read from, and a version with no
 *     recorded evaluation gets an explicit card set that says so — never a zero,
 *     never a dash that reads as "about zero".
 *   * **Promotion is refused with a reason before it is refused by the server.**
 *     A retired version is terminal (R-68) and a version with no training manifest
 *     cannot be promoted (R-63); both are rendered as a disabled control *with the
 *     sentence saying why*, so an operator learns the rule instead of a status code.
 *     The server still decides — this is the reason, not the authority.
 *   * **The confirmation is the model id, typed exactly.** design.md §4.7 asks for
 *     it and the same rule already exists in `ConfirmDialog`'s `confirmPhrase`
 *     (T-402): equality, no trimming, no case folding. Copying the rule here rather
 *     than reusing that component is not a second rule — the promotion modal also
 *     collects a justification, which `ConfirmDialog` has no field for, so the
 *     comparison is exposed as a function and tested against the same cases.
 *   * **What the API cannot supply is named, not omitted.** FR-31's read model is
 *     five scalars with provenance: there is no confusion matrix and no score
 *     distribution in it, and design.md §4.7 asks for both. The comparison panel
 *     says so, and the gap is filed as a task rather than filled with a drawing of
 *     numbers nobody measured.
 */
import type { BadgeTone } from '../../components/ui';
import { formatStamp } from '../../lib/format';
import type { ModelMetrics, ModelVersion } from '../../api/models';

/** The metric names FR-31 defines, in the order a reader expects them. */
export const METRIC_ORDER: readonly string[] = ['roc_auc', 'pr_auc', 'precision', 'recall', 'f1'];

/** How a metric renders. A name with no entry falls back to the raw name. */
export const METRIC_LABELS: Readonly<Record<string, string>> = {
  roc_auc: 'ROC-AUC',
  pr_auc: 'PR-AUC',
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1',
};

/**
 * The longest justification or reason the API accepts.
 *
 * Mirrors `MAX_REASON_LENGTH` in `backend/app/schemas/model.py`; a test reads that
 * file and fails if the two disagree, because a client that allowed more would send
 * a request the API rejects with a 422 nobody can act on.
 */
export const MAX_REASON_LENGTH = 500;

export interface MetricCard {
  name: string;
  label: string;
  /** The value as it renders, at the precision a metric is quoted at. */
  valueText: string;
  /** The recorded run and the field inside it (R-74). */
  provenance: string;
}

export interface VersionRow {
  version: ModelVersion;
  /** `active` first, then `staging`, then `retired`; see `versionRows`. */
  id: string;
  /** The id shortened for the table cell; the full one is always in `title`. */
  shortId: string;
  kind: string;
  kindLabel: string;
  status: string;
  statusLabel: string;
  statusTone: BadgeTone;
  promotedBy: string;
  promotedAt: string;
  manifestLabel: string;
  /** Whether this version may be promoted at all, and why not when it may not. */
  promotable: boolean;
  promotableReason: string | null;
  /** A sentence for a version already serving, so the table is not a wall of ids. */
  servingNote: string | null;
}

const STATUS_TONES: Readonly<Record<string, BadgeTone>> = {
  active: 'benign',
  staging: 'info',
  retired: 'neutral',
};

const STATUS_ORDER: Readonly<Record<string, number>> = {
  active: 0,
  staging: 1,
  retired: 2,
};

const KIND_LABELS: Readonly<Record<string, string>> = {
  flow: 'Flow',
  log: 'Log',
};

/** Title-case a status for display; an unrecognised one is shown as it arrived. */
function label(value: string): string {
  const first = value.slice(0, 1);
  return first === '' ? value : first.toUpperCase() + value.slice(1);
}

/** The first 12 hex characters, the length a reviewer can compare at a glance. */
export function shortId(modelId: string): string {
  return modelId.length <= 12 ? modelId : modelId.slice(0, 12);
}

/**
 * Why a version cannot be promoted, or `null` when it can.
 *
 * Order matters: a retired version with no manifest has two reasons, and the
 * lifecycle rule is the one that cannot be fixed by attaching a manifest.
 */
export function promotionRefusal(version: ModelVersion): string | null {
  if (version.status === 'active') {
    return 'This version is already serving. Promoting it again would change nothing.';
  }
  if (version.status === 'retired') {
    return 'Retired is terminal (R-68), so this version cannot serve again.';
  }
  if (!version.manifest_present) {
    return 'Its artifact has no training manifest, so R-63 refuses its promotion.';
  }
  return null;
}

/**
 * The version table's rows.
 *
 * Sorted rather than left in arrival order: what is serving is what an operator came
 * for, so `active` leads, then what can become active, then history. Ties break on
 * the promotion instant (newest first) and then on the id, so the order is total and
 * a refetch cannot reshuffle two rows with equal rank.
 */
export function versionRows(versions: readonly ModelVersion[]): VersionRow[] {
  const rows = versions.map((version): VersionRow => {
    const refusal = promotionRefusal(version);
    return {
      version,
      id: version.model_id,
      shortId: shortId(version.model_id),
      kind: version.kind,
      kindLabel: KIND_LABELS[version.kind] ?? version.kind,
      status: version.status,
      statusLabel: label(version.status),
      statusTone: STATUS_TONES[version.status] ?? 'neutral',
      promotedBy: version.promoted_by ?? 'not recorded',
      promotedAt:
        version.promoted_at === null ? 'never promoted' : formatStamp(version.promoted_at),
      manifestLabel: version.manifest_present ? 'present' : 'missing',
      promotable: refusal === null,
      promotableReason: refusal,
      servingNote:
        version.status === 'active'
          ? `Serving ${KIND_LABELS[version.kind] ?? version.kind} traffic.`
          : null,
    };
  });

  return rows.sort((left, right) => {
    const rank = (row: VersionRow): number => STATUS_ORDER[row.status] ?? 3;
    if (rank(left) !== rank(right)) return rank(left) - rank(right);
    const leftAt = left.version.promoted_at ?? '';
    const rightAt = right.version.promoted_at ?? '';
    if (leftAt !== rightAt) return rightAt.localeCompare(leftAt);
    return left.id.localeCompare(right.id);
  });
}

/** A metric's display label; an unknown name renders as itself, in order last. */
export function metricLabel(name: string): string {
  return METRIC_LABELS[name] ?? name;
}

/** Metric names in display order: the five FR-31 names, then any others sorted. */
export function metricNames(metrics: ModelMetrics | null): string[] {
  // A payload whose `metrics` map is missing is treated as *no* metrics rather than
  // left to throw: this runs inside a render, and a TypeError there is a blank
  // screen — a worse answer to a malformed response than "nothing was recorded".
  // The dashboard has no runtime schema validation (the client refuses a body that
  // is not JSON, not one that is JSON of the wrong shape), so the total function is
  // where that gets absorbed.
  const named: Record<string, unknown> | undefined = metrics?.metrics;
  if (named === undefined || named === null) return [];
  const names = Object.keys(named);
  const known = METRIC_ORDER.filter((name) => names.includes(name));
  const unknown = names.filter((name) => !METRIC_ORDER.includes(name)).sort();
  return [...known, ...unknown];
}

/** A metric value at the precision it is quoted at: four decimals, as the DB holds. */
export function formatMetric(value: number): string {
  return value.toFixed(4);
}

export interface MetricPanel {
  cards: MetricCard[];
  /** The split and the run date, or why there are no cards. */
  caption: string;
  /** True when the version has no recorded evaluation at all. */
  absent: boolean;
}

/**
 * The metric cards for one version.
 *
 * An absent evaluation is a *state of the panel*, not an empty list: the screen
 * renders the sentence in `caption` where the cards would be, because a blank panel
 * and a zero both read as a measurement.
 */
export function metricPanel(
  metrics: ModelMetrics | null,
  options: { evaluatedAt?: (iso: string) => string } = {},
): MetricPanel {
  if (metrics === null) {
    return {
      cards: [],
      caption:
        'No recorded evaluation is attached to this version, so FR-31 has no numbers to show. ' +
        'A value without a run would be a claim, not a measurement (R-74).',
      absent: true,
    };
  }
  const stamp = options.evaluatedAt ?? formatStamp;
  const cards: MetricCard[] = [];
  for (const name of metricNames(metrics)) {
    const point = metrics.metrics[name];
    // A metric without a numeric value cannot be rendered as a measurement (R-74).
    if (point === undefined || typeof point.value !== 'number') continue;
    cards.push({
      name,
      label: metricLabel(name),
      valueText: formatMetric(point.value),
      provenance: `read from ${point.artifact} at ${point.field}`,
    });
  }
  return {
    cards,
    caption: `Measured on ${metrics.split}, evaluated ${stamp(metrics.evaluated_at)}.`,
    absent: false,
  };
}

export interface ComparisonCell {
  name: string;
  label: string;
  /** The left/right values, or `null` where that version has no such metric. */
  left: number | null;
  right: number | null;
  /** The signed delta, or `null` unless both sides have the metric. */
  delta: number | null;
  deltaText: string;
  /** Which side is better is not this function's business; it reports, not judges. */
  direction: 'up' | 'down' | 'equal' | 'unknown';
}

export interface Comparison {
  cells: ComparisonCell[];
  /** What the read model cannot answer, said once (R-70's discipline). */
  note: string;
}

/** A delta rendered with its sign, so "up" and "down" are visible at a glance. */
export function formatDelta(delta: number): string {
  if (delta === 0) return '0.0000';
  return `${delta > 0 ? '+' : '−'}${Math.abs(delta).toFixed(4)}`;
}

/**
 * Two versions side by side, per metric.
 *
 * The cells are the union of both versions' metric names, so a metric only one side
 * has is visible *as* missing rather than silently dropped — which is the failure a
 * zip of two lists produces. A delta exists only where both sides have a number;
 * differencing a value against nothing would be arithmetic on a hole.
 */
export function compareVersions(left: ModelMetrics | null, right: ModelMetrics | null): Comparison {
  const names = [...new Set([...metricNames(left), ...metricNames(right)])];
  const cells = names.map((name): ComparisonCell => {
    const leftValue = left?.metrics?.[name]?.value ?? null;
    const rightValue = right?.metrics?.[name]?.value ?? null;
    const both = leftValue !== null && rightValue !== null;
    const delta = both ? rightValue - leftValue : null;
    return {
      name,
      label: metricLabel(name),
      left: leftValue,
      right: rightValue,
      delta,
      deltaText: delta === null ? 'not comparable — one side has no value' : formatDelta(delta),
      direction: delta === null ? 'unknown' : delta > 0 ? 'up' : delta < 0 ? 'down' : 'equal',
    };
  });
  return {
    cells,
    note:
      'Confusion matrices and score-distribution histograms are part of design.md §4.7 but not ' +
      'of the recorded metrics: FR-31\u2019s read model is five scalars, each with the run it came ' +
      'from. Drawing either from these numbers would be inventing data, so the comparison shows ' +
      'the deltas it can support (filed as T-420).',
  };
}

export interface PromotionDraft {
  /** What the operator typed into the confirmation field. */
  typedId: string;
  /** The version's id, exactly as the table shows it. */
  modelId: string;
  justification: string;
}

export interface PromotionReadiness {
  ready: boolean;
  /** Why not, in the operator's terms — the same sentence the button's title uses. */
  reason: string | null;
}

/**
 * Whether a promotion may be submitted.
 *
 * The id must match **exactly** — `ConfirmDialog`'s rule (T-402): no trimming, no
 * case folding. A confirmation that accepts a near miss is a confirmation that
 * accepts the wrong model when two ids differ in one character.
 */
export function promotionReadiness(draft: PromotionDraft): PromotionReadiness {
  if (draft.modelId === '') return { ready: false, reason: 'No version is selected.' };
  if (draft.typedId !== draft.modelId) {
    return { ready: false, reason: 'Type the model id exactly to confirm.' };
  }
  if (draft.justification.trim() === '') {
    return { ready: false, reason: 'A promotion needs a written justification.' };
  }
  if (draft.justification.length > MAX_REASON_LENGTH) {
    return {
      ready: false,
      reason: `The justification may be at most ${String(MAX_REASON_LENGTH)} characters.`,
    };
  }
  return { ready: true, reason: null };
}

/**
 * Kinds that have an active version, i.e. kinds a rollback could be attempted on.
 *
 * The server is still the authority — it answers 409 when there is nothing to roll
 * back to — but a control that cannot apply is not offered, and the reason is kept
 * for the case where the operator asks anyway.
 */
export function rollbackKinds(versions: readonly { status: string; kind: string }[]): string[] {
  const kinds = new Set<string>();
  for (const version of versions) {
    if (version.status === 'active') kinds.add(version.kind);
  }
  return [...kinds].sort();
}

/** The most recent transition, for the screen's confirmation sentence. */
export function transitionSentence(transition: {
  model_id: string;
  retired: string | null;
  changed: boolean;
}): string {
  if (!transition.changed) {
    return `${shortId(transition.model_id)} was already serving, so nothing changed and the audit trail recorded nothing (FR-42).`;
  }
  const retired =
    transition.retired === null
      ? 'nothing was serving before it'
      : `${shortId(transition.retired)} stepped down`;
  return `${shortId(transition.model_id)} is now serving; ${retired}.`;
}
