/**
 * The retention panel's derived model (T-410, NFR-05, design.md §4.8).
 *
 * `GET /api/v1/retention` returns a *plan*: what a run would drop, and three lists
 * that exist to stop the plan being read as a clean bill of health —
 * `missing` (months inside the window with no partition, which means rows were
 * rejected at insert), `unevictable` (partitions a drop cannot reach) and `external`
 * (stores outside the database, which no plan can reach at all). A retention screen
 * that showed only the drop list would be reporting the easy half of the answer.
 *
 * The plan's statements are shown, not hidden: they are DDL naming partitions, and
 * they are what makes "a month was dropped" mean a specific month.
 */
import { formatStamp } from '../../lib/format';
import type { RetentionPlan, RetentionRun, Unevictable, WindowPartition } from '../../api/admin';

export interface PartitionRow {
  name: string;
  table: string;
  covers: string;
  statement: string;
}

export function partitionRows(partitions: readonly WindowPartition[] | undefined): PartitionRow[] {
  return (partitions ?? []).map((partition) => ({
    name: partition.name,
    table: partition.table,
    covers: `${partition.covers_start} → ${partition.covers_end}`,
    statement: partition.statement,
  }));
}

export interface UnevictableRow extends Unevictable {
  /** The reason as a sentence, since the server's is a short slug. */
  explains: string;
}

const UNEVICTABLE_TEXT: Readonly<Record<string, string>> = {
  'no-partition': 'Not a partitioned table: only monthly partitions can be dropped whole.',
  'not-monthly': 'Its partitions are not monthly, so a retention window does not bound them.',
  'current-month': 'This month is inside the window and is still being written to.',
  'attached-elsewhere':
    'Its partition is attached to another table, so a drop would take that one too.',
};

export function unevictableRows(rows: readonly Unevictable[] | undefined): UnevictableRow[] {
  return (rows ?? []).map((row) => ({
    ...row,
    explains: UNEVICTABLE_TEXT[row.reason] ?? row.reason,
  }));
}

/** What the panel says above the plan, and what an operator should worry about. */
export interface RetentionReading {
  policy: string;
  drop: string;
  kept: string;
  warnings: string[];
  plannedAt: string;
}

export function readRetention(plan: RetentionPlan | undefined): RetentionReading {
  if (plan === undefined) {
    return { policy: '', drop: '', kept: '', warnings: [], plannedAt: '' };
  }
  const policy =
    `Raw records ${String(plan.policy.raw_records_days)} days, ` +
    `alerts ${String(plan.policy.alerts_days)} days, ` +
    `stats ${String(plan.policy.stats_days)} days.`;
  const warnings: string[] = [];
  if (plan.missing.length > 0) {
    warnings.push(
      `${plan.missing.join(', ')} ${plan.missing.length === 1 ? 'has' : 'have'} no partition. There is no default partition, so rows for ${plan.missing.length === 1 ? 'that month' : 'those months'} were rejected at insert — a gap the counts cannot show.`,
    );
  }
  if (plan.unevictable.length > 0) {
    warnings.push(
      `${String(plan.unevictable.length)} table${plan.unevictable.length === 1 ? '' : 's'} can never be evicted by a partition drop. A run does not touch ${plan.unevictable.length === 1 ? 'it' : 'them'}.`,
    );
  }
  if (Object.keys(plan.external).length > 0) {
    const stores = Object.entries(plan.external)
      .map(([store, detail]) => `${store} (${detail})`)
      .join('; ');
    warnings.push(`Outside the database, and therefore outside every plan: ${stores}.`);
  }
  return {
    policy,
    drop:
      plan.drop.length === 0
        ? 'Nothing is past its window: a run would drop no partition.'
        : `${String(plan.drop.length)} partition${plan.drop.length === 1 ? '' : 's'} would be dropped.`,
    kept: `${String(plan.kept.length)} partition${plan.kept.length === 1 ? '' : 's'} stay inside the window.`,
    warnings,
    plannedAt: formatStamp(plan.planned_at),
  };
}

/** What a completed run did, including the nothing-to-do case. */
export function readRun(run: RetentionRun | undefined): string {
  if (run === undefined) return '';
  if (!run.changed_anything) {
    return run.planned.length === 0
      ? 'The run found nothing to drop. No partition was affected, and the trail records the run.'
      : `Every planned partition (${run.planned.join(', ')}) was already absent. Nothing changed.`;
  }
  const parts = [`Dropped ${run.dropped.join(', ')}.`];
  if (run.already_absent.length > 0) {
    parts.push(`Already absent: ${run.already_absent.join(', ')}.`);
  }
  return `${parts.join(' ')} The trail records the run (FR-42).`;
}
