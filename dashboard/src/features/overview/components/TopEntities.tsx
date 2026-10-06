/**
 * Top attacked entities (design.md §4.1, FR-50).
 *
 * Ranked by alert count, with the peak severity shown as a pill rather than a
 * colour on the row: §4.1's sketch shows the same, and a list where severity is a
 * background tint is a list that cannot be read by anyone who cannot see the tint.
 *
 * **The names are missing, and the panel says so.** The query API returns
 * `entity_id` and nothing else — the `entities` table holds the host or user value
 * but no endpoint exposes it — so the rows read `entity 142`. An operator needs the
 * hostname, which is why the gap is filed (T-416) and stated here instead of being
 * dressed up as a complete panel.
 */
import { SeverityPill } from '../../../components/ui';
import { formatCount } from '../../../lib/format';
import type { EntitySummary } from '../aggregate';

export interface TopEntitiesProps {
  entities: readonly EntitySummary[];
  windowLabel: string;
}

export function TopEntities({ entities, windowLabel }: TopEntitiesProps) {
  return (
    <div>
      <p className="mb-2 text-caption text-muted">{windowLabel}</p>
      <ol className="flex flex-col">
        {entities.map((entity, index) => (
          <li
            key={entity.entityId}
            className="flex items-baseline justify-between gap-3 border-b border-line/50 py-2"
          >
            <span className="flex items-baseline gap-2">
              <span className="text-caption tabular-nums text-muted">{index + 1}.</span>
              <span className="font-mono text-body-sm text-ink">entity {entity.entityId}</span>
            </span>
            <span className="flex items-baseline gap-3">
              <span className="text-caption tabular-nums text-muted">
                {formatCount(entity.alerts)} alerts · {formatCount(entity.occurrences)} occurrences
              </span>
              {entity.peak === null ? null : <SeverityPill severity={entity.peak} />}
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-caption text-muted">
        Entity names are not exposed by the query API yet (T-416), so rows are keyed by id.
      </p>
    </div>
  );
}
