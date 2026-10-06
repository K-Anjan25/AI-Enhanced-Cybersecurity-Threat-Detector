/**
 * The retention model (T-410, NFR-05).
 *
 * The plan's three awkward lists are the reason this file exists: `missing`,
 * `unevictable` and `external` are the stores a run cannot reach, and a screen that
 * rendered only the drop list would report the easy half of the answer as the whole
 * one. Each gets a warning sentence, and the sentences are asserted here rather than
 * left to the markup.
 */
import { describe, expect, it } from 'vitest';

import type { RetentionPlan, RetentionRun, WindowPartition } from '../../api/admin';
import { partitionRows, readRetention, readRun, unevictableRows } from './retention';

function partition(over: Partial<WindowPartition> = {}): WindowPartition {
  return {
    table: 'raw_records',
    name: 'raw_records_2025_03',
    year: 2025,
    month: 3,
    covers_start: '2025-03-01',
    covers_end: '2025-04-01',
    statement: 'DROP TABLE IF EXISTS raw_records_2025_03',
    ...over,
  };
}

function plan(over: Partial<RetentionPlan> = {}): RetentionPlan {
  return {
    planned_at: '2026-10-06T00:00:00Z',
    policy: { raw_records_days: 365, alerts_days: 400, stats_days: 730 },
    drop: [partition()],
    kept: [],
    missing: [],
    unevictable: [],
    external: {},
    statements: [],
    ...over,
  };
}

describe('partitionRows', () => {
  it('shows the span a partition covers, so a month means a date range', () => {
    expect(partitionRows([partition()])[0]?.covers).toBe('2025-03-01 → 2025-04-01');
  });

  it('keeps the statement, which is what makes the drop specific', () => {
    expect(partitionRows([partition()])[0]?.statement).toContain('DROP TABLE');
  });

  it('is empty for a plan with no drops', () => {
    expect(partitionRows(undefined)).toEqual([]);
  });
});

describe('readRetention', () => {
  it('reads the policy in days for each class of data', () => {
    expect(readRetention(plan()).policy).toBe(
      'Raw records 365 days, alerts 400 days, stats 730 days.',
    );
  });

  it('counts the partitions a run would drop', () => {
    expect(readRetention(plan()).drop).toBe('1 partition would be dropped.');
    expect(readRetention(plan({ drop: [partition(), partition({ name: 'x' })] })).drop).toBe(
      '2 partitions would be dropped.',
    );
  });

  it('says nothing is past its window rather than "0 partitions"', () => {
    expect(readRetention(plan({ drop: [] })).drop).toContain('Nothing is past its window');
  });

  it('warns about a month with no partition, and says rows were rejected', () => {
    const warnings = readRetention(plan({ missing: ['2025-02'] })).warnings;
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('2025-02 has no partition');
    expect(warnings[0]).toContain('rejected at insert');
  });

  it('warns about storage a partition drop can never reach', () => {
    const warnings = readRetention(
      plan({ unevictable: [{ table: 'audit_log', name: 'audit_log', reason: 'not-monthly' }] }),
    ).warnings;
    expect(warnings[0]).toContain('can never be evicted');
  });

  it('names the stores outside the database, which no plan reaches', () => {
    const warnings = readRetention(
      plan({ external: { object_store: 'raw flow archives, 365 days' } }),
    ).warnings;
    expect(warnings[0]).toContain('object_store (raw flow archives, 365 days)');
  });

  it('is silent when there is nothing to warn about', () => {
    expect(readRetention(plan()).warnings).toEqual([]);
  });

  it('reads an unread plan as empty text, never as "nothing to drop"', () => {
    const empty = readRetention(undefined);
    expect(empty).toEqual({ policy: '', drop: '', kept: '', warnings: [], plannedAt: '' });
  });
});

describe('unevictableRows', () => {
  it('explains a known reason in a sentence', () => {
    const rows = unevictableRows([{ table: 't', name: 't', reason: 'not-monthly' }]);
    expect(rows[0]?.explains).toBe(
      'Its partitions are not monthly, so a retention window does not bound them.',
    );
  });

  it('passes an unknown reason through rather than inventing an explanation', () => {
    const rows = unevictableRows([{ table: 't', name: 't', reason: 'because' }]);
    expect(rows[0]?.explains).toBe('because');
  });
});

describe('readRun', () => {
  function run(over: Partial<RetentionRun> = {}): RetentionRun {
    return {
      started_at: '2026-10-06T00:00:00Z',
      planned: ['raw_records_2025_03'],
      dropped: ['raw_records_2025_03'],
      already_absent: [],
      changed_anything: true,
      ...over,
    };
  }

  it('names what was dropped and says the run is recorded', () => {
    const text = readRun(run());
    expect(text).toContain('Dropped raw_records_2025_03.');
    expect(text).toContain('trail records the run');
  });

  it('reports a run that changed nothing as a no-op, not as a success with drops', () => {
    const text = readRun(
      run({ dropped: [], already_absent: ['raw_records_2025_03'], changed_anything: false }),
    );
    expect(text).toContain('already absent');
    expect(text).toContain('Nothing changed');
  });

  it('says a run with no plan found nothing to do', () => {
    const text = readRun(run({ planned: [], dropped: [], changed_anything: false }));
    expect(text).toContain('found nothing to drop');
  });

  it('is empty before a run', () => {
    expect(readRun(undefined)).toBe('');
  });
});
