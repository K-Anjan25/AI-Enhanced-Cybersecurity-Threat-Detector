/**
 * @vitest-environment node
 */
/**
 * The model ops derived model (T-409).
 *
 * Two of these assertions read the *other* half of the system rather than restating
 * it: `MAX_REASON_LENGTH` is compared with the backend's `MAX_REASON_LENGTH`, and the
 * exact-match confirmation is tested against the same cases `ConfirmDialog` handles
 * (T-402), because a client whose limits drift from the API's produces a 422 the
 * operator cannot act on.
 *
 * The rest is the behaviour a screen would otherwise re-implement: ordering, refusal
 * reasons, provenance on every metric, and the union rules of the comparison.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { ModelMetrics, ModelVersion } from '../../api/models';
import {
  MAX_REASON_LENGTH,
  METRIC_ORDER,
  compareVersions,
  formatDelta,
  formatMetric,
  metricNames,
  metricPanel,
  promotionReadiness,
  promotionRefusal,
  rollbackKinds,
  shortId,
  transitionSentence,
  versionRows,
} from './versions';

const MODEL = 'a'.repeat(64);
const OTHER = 'b'.repeat(64);

function version(overrides: Partial<ModelVersion> = {}): ModelVersion {
  return {
    model_id: MODEL,
    kind: 'flow',
    status: 'staging',
    artifact_uri: 's3://aegis/models/flow/1',
    sha256: 'c'.repeat(64),
    manifest_present: true,
    metrics: null,
    promoted_at: null,
    promoted_by: null,
    justification: '',
    ...overrides,
  };
}

function metrics(values: Record<string, number>): ModelMetrics {
  return {
    split: 'temporal:2025-Q4',
    evaluated_at: '2026-09-30T12:00:00Z',
    metrics: Object.fromEntries(
      Object.entries(values).map(([name, value]) => [
        name,
        { value, artifact: `runs/${name}.json`, field: `test.${name}` },
      ]),
    ),
  };
}

describe('shortId', () => {
  it('shortens a content address to a comparable prefix', () => {
    expect(shortId(MODEL)).toBe('aaaaaaaaaaaa');
    expect(shortId(MODEL)).toHaveLength(12);
  });

  it('leaves a short id alone rather than padding it', () => {
    expect(shortId('abc')).toBe('abc');
  });
});

describe('promotionRefusal', () => {
  it('refuses an already-active version as a no-op', () => {
    expect(promotionRefusal(version({ status: 'active' }))).toContain('already serving');
  });

  it('refuses a retired version with R-68 by name', () => {
    const reason = promotionRefusal(version({ status: 'retired' }));
    expect(reason).toContain('terminal');
    expect(reason).toContain('R-68');
  });

  it('refuses a version whose artifact has no manifest, naming R-63', () => {
    const reason = promotionRefusal(version({ manifest_present: false }));
    expect(reason).toContain('manifest');
    expect(reason).toContain('R-63');
  });

  it('reports the lifecycle rule first when both apply', () => {
    // A retired version with no manifest has two reasons; the one that cannot be
    // fixed by attaching a manifest is the answer.
    const reason = promotionRefusal(version({ status: 'retired', manifest_present: false }));
    expect(reason).toContain('R-68');
    expect(reason).not.toContain('R-63');
  });

  it('permits a staging version with a manifest', () => {
    expect(promotionRefusal(version())).toBeNull();
  });
});

describe('versionRows', () => {
  it('orders active, then staging, then retired', () => {
    const rows = versionRows([
      version({ model_id: '1'.repeat(64), status: 'retired', promoted_at: '2026-09-01T00:00:00Z' }),
      version({ model_id: '2'.repeat(64), status: 'staging' }),
      version({ model_id: '3'.repeat(64), status: 'active', promoted_at: '2026-09-20T00:00:00Z' }),
    ]);
    expect(rows.map((row) => row.status)).toEqual(['active', 'staging', 'retired']);
  });

  it('breaks ties on the promotion instant, newest first, then the id', () => {
    const rows = versionRows([
      version({ model_id: '2'.repeat(64), status: 'retired', promoted_at: '2026-09-01T00:00:00Z' }),
      version({ model_id: '1'.repeat(64), status: 'retired', promoted_at: '2026-09-01T00:00:00Z' }),
      version({ model_id: '3'.repeat(64), status: 'retired', promoted_at: '2026-09-10T00:00:00Z' }),
    ]);
    expect(rows.map((row) => row.id[0])).toEqual(['3', '1', '2']);
  });

  it('says “not recorded” rather than inventing a promoter', () => {
    const [row] = versionRows([version()]);
    expect(row?.promotedBy).toBe('not recorded');
    expect(row?.promotedAt).toBe('never promoted');
  });

  it('marks a version serving its kind', () => {
    const [row] = versionRows([version({ status: 'active', kind: 'log' })]);
    expect(row?.servingNote).toBe('Serving Log traffic.');
  });

  it('tone-maps the three states and falls back to neutral for an unknown one', () => {
    const rows = versionRows([
      version({ model_id: '1'.repeat(64), status: 'active' }),
      version({ model_id: '2'.repeat(64), status: 'staging' }),
      version({ model_id: '3'.repeat(64), status: 'retired' }),
      version({ model_id: '4'.repeat(64), status: 'quarantined' }),
    ]);
    const tone = (id: string): string =>
      rows.find((row) => row.id.startsWith(id))?.statusTone ?? '';
    expect(tone('1')).toBe('benign');
    expect(tone('2')).toBe('info');
    expect(tone('3')).toBe('neutral');
    // An unknown state renders as itself rather than being hidden or renamed.
    expect(tone('4')).toBe('neutral');
    expect(rows.find((row) => row.id.startsWith('4'))?.statusLabel).toBe('Quarantined');
  });
});

describe('promotionReadiness', () => {
  it('requires the id to match exactly, with no trimming', () => {
    expect(promotionReadiness({ typedId: MODEL, modelId: MODEL, justification: 'why' }).ready).toBe(
      true,
    );
    expect(
      promotionReadiness({ typedId: ` ${MODEL}`, modelId: MODEL, justification: 'why' }).ready,
    ).toBe(false);
    expect(
      promotionReadiness({ typedId: MODEL.slice(0, -1), modelId: MODEL, justification: 'why' })
        .ready,
    ).toBe(false);
    expect(
      promotionReadiness({ typedId: MODEL.toUpperCase(), modelId: MODEL, justification: 'why' })
        .ready,
    ).toBe(false);
  });

  it('requires a justification that is not whitespace', () => {
    expect(promotionReadiness({ typedId: MODEL, modelId: MODEL, justification: '' }).reason).toBe(
      'A promotion needs a written justification.',
    );
    expect(promotionReadiness({ typedId: MODEL, modelId: MODEL, justification: '   ' }).ready).toBe(
      false,
    );
  });

  it('refuses more characters than the API accepts', () => {
    const draft = {
      typedId: MODEL,
      modelId: MODEL,
      justification: 'x'.repeat(MAX_REASON_LENGTH + 1),
    };
    expect(promotionReadiness(draft).ready).toBe(false);
    expect(
      promotionReadiness({ ...draft, justification: 'x'.repeat(MAX_REASON_LENGTH) }).ready,
    ).toBe(true);
  });

  it('refuses to confirm when no version is selected', () => {
    expect(promotionReadiness({ typedId: '', modelId: '', justification: 'why' }).reason).toBe(
      'No version is selected.',
    );
  });

  it('keeps MAX_REASON_LENGTH equal to the backend’s, so a valid form cannot 422', () => {
    const schema = readFileSync(
      fileURLToPath(new URL('../../../../backend/app/schemas/model.py', import.meta.url)),
      'utf8',
    );
    const match = /^MAX_REASON_LENGTH = (\d+)$/m.exec(schema);
    expect(match, 'MAX_REASON_LENGTH is not a literal in the backend schema').not.toBeNull();
    expect(Number(match?.[1])).toBe(MAX_REASON_LENGTH);
  });
});

describe('metric naming', () => {
  it('orders the five FR-31 names, then unknown names alphabetically', () => {
    expect(metricNames(metrics({ recall: 1, f1: 1, zzz: 1, pr_auc: 1, aaa: 1 }))).toEqual([
      'pr_auc',
      'recall',
      'f1',
      'aaa',
      'zzz',
    ]);
    expect(METRIC_ORDER).toEqual(['roc_auc', 'pr_auc', 'precision', 'recall', 'f1']);
  });

  it('formats at the precision the database holds', () => {
    expect(formatMetric(0.81234)).toBe('0.8123');
  });
});

describe('metricPanel', () => {
  it('is explicit about an absent evaluation rather than an empty grid', () => {
    const panel = metricPanel(null);
    expect(panel.absent).toBe(true);
    expect(panel.cards).toEqual([]);
    expect(panel.caption).toContain('R-74');
  });

  it('carries the run and the field on every card (R-74)', () => {
    const panel = metricPanel(metrics({ roc_auc: 0.81, recall: 0.44 }));
    expect(panel.absent).toBe(false);
    expect(panel.cards.map((card) => card.label)).toEqual(['ROC-AUC', 'Recall']);
    expect(panel.cards[0]?.valueText).toBe('0.8100');
    expect(panel.cards[0]?.provenance).toBe('read from runs/roc_auc.json at test.roc_auc');
  });

  it('names the split and the run date in the caption', () => {
    const panel = metricPanel(metrics({ f1: 0.5 }));
    expect(panel.caption).toContain('temporal:2025-Q4');
    expect(panel.caption).toContain('2026');
  });

  it('treats a payload with no metrics map as no metrics, rather than throwing in a render', () => {
    // A malformed response must not blank the screen: the panel says nothing was
    // recorded, which is a fact about this version, not about the response.
    const malformed = {
      split: 'temporal:2025-Q4',
      evaluated_at: '2026-09-30T12:00:00Z',
    } as ModelMetrics;
    expect(metricNames(malformed)).toEqual([]);
    expect(metricPanel(malformed).cards).toEqual([]);
    expect(compareVersions(malformed, null).cells).toEqual([]);
  });

  it('skips a metric whose value is not a number', () => {
    const broken = {
      split: 's',
      evaluated_at: '2026-09-30T12:00:00Z',
      metrics: { f1: { artifact: 'a', field: 'b' } },
    } as unknown as ModelMetrics;
    expect(metricPanel(broken).cards).toEqual([]);
  });

  it('renders one card per recorded metric', () => {
    const sparse: ModelMetrics = {
      split: 'temporal:2025-Q4',
      evaluated_at: '2026-09-30T12:00:00Z',
      metrics: { f1: { value: 0.5, artifact: 'a', field: 'b' } },
    };
    expect(metricPanel(sparse).cards.map((card) => card.name)).toEqual(['f1']);
  });
});

describe('compareVersions', () => {
  it('deltas only where both sides have a value', () => {
    const comparison = compareVersions(
      metrics({ roc_auc: 0.8, f1: 0.6 }),
      metrics({ roc_auc: 0.9 }),
    );
    const roc = comparison.cells.find((cell) => cell.name === 'roc_auc');
    const f1 = comparison.cells.find((cell) => cell.name === 'f1');
    expect(roc?.delta).toBeCloseTo(0.1, 10);
    expect(roc?.direction).toBe('up');
    expect(f1?.delta).toBeNull();
    expect(f1?.deltaText).toContain('not comparable');
  });

  it('shows a metric only one side has instead of dropping it', () => {
    const comparison = compareVersions(metrics({ roc_auc: 0.8 }), metrics({ pr_auc: 0.4 }));
    expect(comparison.cells.map((cell) => cell.name).sort()).toEqual(['pr_auc', 'roc_auc']);
  });

  it('handles an absent side without inventing deltas', () => {
    const comparison = compareVersions(null, metrics({ roc_auc: 0.9 }));
    expect(comparison.cells[0]?.delta).toBeNull();
    expect(comparison.cells[0]?.right).toBe(0.9);
  });

  it('names what the read model cannot supply', () => {
    const comparison = compareVersions(metrics({ f1: 0.5 }), metrics({ f1: 0.6 }));
    expect(comparison.note).toContain('Confusion matrices');
    expect(comparison.note).toContain('T-420');
  });

  it('renders a signed delta with a real minus sign', () => {
    expect(formatDelta(0.0001)).toBe('+0.0001');
    expect(formatDelta(-0.0001)).toBe('−0.0001');
    expect(formatDelta(0)).toBe('0.0000');
  });
});

describe('rollbackKinds', () => {
  it('offers only kinds that have something serving', () => {
    expect(
      rollbackKinds([
        { kind: 'flow', status: 'active' },
        { kind: 'log', status: 'staging' },
        { kind: 'flow', status: 'retired' },
      ]),
    ).toEqual(['flow']);
  });

  it('is empty for a registry with nothing active', () => {
    expect(rollbackKinds([{ kind: 'flow', status: 'staging' }])).toEqual([]);
  });
});

describe('transitionSentence', () => {
  it('says a no-op recorded nothing, which is the part an operator would assume wrongly', () => {
    const sentence = transitionSentence({ model_id: MODEL, retired: null, changed: false });
    expect(sentence).toContain('nothing changed');
    expect(sentence).toContain('recorded nothing');
  });

  it('names the version that stepped down', () => {
    const sentence = transitionSentence({ model_id: MODEL, retired: OTHER, changed: true });
    expect(sentence).toContain('bbbbbbbbbbbb');
    expect(sentence).toContain('stepped down');
  });

  it('says when nothing was serving before', () => {
    expect(transitionSentence({ model_id: MODEL, retired: null, changed: true })).toContain(
      'nothing was serving before it',
    );
  });
});
