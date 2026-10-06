/**
 * The KPI tiles (design.md §4.1).
 *
 * Five tiles: three severity counts, the open-alert count, and mean time to
 * verdict. The first four are read straight out of the alert window; the fifth has
 * no source in this build, and says so on its face rather than showing a zero that
 * would read as "verdicts are instant".
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
  severity?: Severity | undefined;
}

export interface KpiTilesProps {
  tiles: readonly Tile[];
  /** How much of the window was actually read; a partial count says so. */
  partial: boolean;
}

export function KpiTiles({ tiles, partial }: KpiTilesProps) {
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
          </dd>
          <dd className="mt-1 text-caption text-muted">
            {tile.caption}
            {partial && tile.value !== null ? ' · partial coverage' : ''}
          </dd>
        </div>
      ))}
    </dl>
  );
}
