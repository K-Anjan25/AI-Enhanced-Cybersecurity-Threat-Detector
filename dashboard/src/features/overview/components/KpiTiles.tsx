/**
 * The KPI tiles (design.md §4.1).
 *
 * Five tiles: three severity counts, the open-alert count, and mean time to
 * verdict. All five come from the same aggregate (T-416), so no tile can disagree
 * with the chart below it — and the verdict tile says what its mean covers rather
 * than showing a figure whose basis is invisible.
 *
 * Numbers are `font.mono` with tabular figures (§5.4) so the tiles do not jitter as
 * they refresh, and each severity tile keeps the palette's ordering rather than the
 * alphabet's — critical first, because that is the order an operator reads.
 */
import { SeverityPill, type Severity } from '../../../components/ui';
import { formatCount } from '../../../lib/format';

export interface Tile {
  label: string;
  value: number | null;
  /** A short line under the value: the window, a target, or why it is absent. */
  caption: string;
  /** The unit the value is in, rendered beside it (e.g. `s`). */
  unit?: string | undefined;
  severity?: Severity | undefined;
}

export interface KpiTilesProps {
  tiles: readonly Tile[];
}

export function KpiTiles({ tiles }: KpiTilesProps) {
  return (
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      {tiles.map((tile) => (
        <div key={tile.label} className="rounded-card border border-line bg-base p-4">
          <dt className="flex items-center gap-2">
            {tile.severity === undefined ? (
              <span className="text-caption uppercase tracking-wide text-muted">{tile.label}</span>
            ) : (
              <SeverityPill severity={tile.severity} />
            )}
          </dt>
          <dd className="mt-2 text-display font-semibold tabular-nums text-ink">
            {tile.value === null ? '—' : formatCount(tile.value)}
            {tile.unit === undefined || tile.value === null ? null : (
              <span className="ml-1 text-body-sm text-muted">{tile.unit}</span>
            )}
          </dd>
          <dd className="mt-1 text-caption text-muted">{tile.caption}</dd>
        </div>
      ))}
    </dl>
  );
}
