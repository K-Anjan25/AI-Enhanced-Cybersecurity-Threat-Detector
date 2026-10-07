/**
 * Top attacked entities (design.md §4.1, FR-50, T-416).
 *
 * Each row is the entity the window's alerts were about: the `entities` table's
 * `kind` and `value` — `host web-01.corp`, `user j.doe@corp` — with the alert and
 * occurrence counts and the peak severity as a pill rather than a colour on the
 * row, because a list where severity is a background tint cannot be read by anyone
 * who cannot see the tint.
 *
 * **An id with no name says so.** The endpoint names what the registry has seen,
 * and a process that started after those alerts did cannot name everything. Such a
 * row reads `entity 142` and the panel's note says what that means, rather than
 * presenting an id as if it were a hostname.
 *
 * **A capped list says it is one.** The list is a top-N *of a complete grouping*:
 * when the window held more entities than the panel draws, `capped` is true and the
 * note says "top N of more" rather than letting five rows read as the population.
 */
import { SeverityPill } from '../../../components/ui';
import { formatCount } from '../../../lib/format';
import type { EntitySummary } from '../aggregate';

export interface TopEntitiesProps {
  entities: readonly EntitySummary[];
  windowLabel: string;
  /** Whether the window held more entities than the list shows. */
  capped: boolean;
}

export function TopEntities({ entities, windowLabel, capped }: TopEntitiesProps) {
  const unnamed = entities.filter((entity) => !entity.named).length;

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
              {entity.named ? (
                <>
                  <span className="text-caption text-muted">{entity.kind}</span>
                  <span className="font-mono text-body-sm text-ink">{entity.value}</span>
                </>
              ) : (
                <span className="font-mono text-body-sm text-ink">entity {entity.entityId}</span>
              )}
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
        {capped ? 'The busiest entities; the window held more. ' : ''}
        {unnamed === 0
          ? 'Every id is named by the entity registry.'
          : `${String(unnamed)} of these ids the entity registry has not seen, so they are shown by id.`}
      </p>
    </div>
  );
}
