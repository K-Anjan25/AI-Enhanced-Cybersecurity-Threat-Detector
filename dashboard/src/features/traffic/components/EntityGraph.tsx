/**
 * The entity graph (design.md §4.4), and the switch that replaces it at scale.
 *
 * §4.4 asks for two things in one breath: a force-directed graph, and a static
 * fallback "for >2,000 nodes (a force simulation at that size is unusable — we
 * switch to a ranked adjacency matrix **and say so**)". So this component has two
 * renderers and no third state, and the label is rendered with the mode rather than
 * chosen by it:
 *
 *   * `force` — an SVG of circles and lines, node radius from the entity's volume
 *     (area-scaled, `graph.ts`), fill from its peak severity, edge width from the
 *     shared-trace count. Hovering shows the numbers in a native `<title>`, and
 *     clicking a node pins it.
 *   * `adjacency` — a ranked matrix over the most active entities, with the reason
 *     string and the "showing N of M" count rendered above it, because a matrix
 *     without that sentence looks like the whole graph.
 *
 * The layout is computed once per data change with a fixed tick count and no timer
 * (`layoutGraph`), so the picture is reproducible — and because it is
 * never animated, `reducedMotion` needs no flag here: there is no motion for a
 * reader to opt out of.
 */
import { useMemo } from 'react';

import { Badge, EmptyState } from '../../../components/ui';
import type { ChartPalette } from '../../../components/charts/palette';
import { formatInstant } from '../../../lib/format';
import { adjacencyMatrix, layoutGraph, type GraphModel } from '../graph';

export interface EntityGraphProps {
  model: GraphModel;
  palette: ChartPalette;
  /** The pinned entity, or `null`. Clicking a node toggles it. */
  pinnedEntityId: number | null;
  onPin: (entityId: number | null) => void;
  width?: number;
  height?: number;
}

export function EntityGraph({
  model,
  palette,
  pinnedEntityId,
  onPin,
  width = 520,
  height = 360,
}: EntityGraphProps) {
  const layout = useMemo(() => layoutGraph(model, { width, height }), [model, width, height]);
  const matrix = useMemo(
    () => (model.mode === 'adjacency' ? adjacencyMatrix(model) : null),
    [model],
  );

  if (model.nodes.length === 0) {
    return (
      <EmptyState
        title="No entities in this selection"
        description="Widen the brush or lower the record threshold to bring entities back into view."
      />
    );
  }

  return (
    <div>
      <p className="mb-2 text-caption text-muted" data-testid="graph-mode">
        {model.reason}
      </p>

      {/* `group`, not `img`: the nodes are buttons, and a presentational `img` role
          would hide every one of them from assistive technology. */}
      {matrix === null ? (
        <svg
          role="group"
          aria-label={`Entity relationships: ${String(model.nodes.length)} entities, ${String(model.edges.length)} relationships. ${model.reason}`}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          className="w-full"
        >
          {layout.edges.map((edge) => (
            <line
              key={`${String(edge.edge.source)}-${String(edge.edge.target)}`}
              x1={edge.source.x}
              y1={edge.source.y}
              x2={edge.target.x}
              y2={edge.target.y}
              stroke={palette.grid}
              strokeWidth={Math.min(4, 0.5 + edge.edge.sharedTraces)}
              data-testid={`edge-${String(edge.edge.source)}-${String(edge.edge.target)}`}
            />
          ))}

          {layout.nodes.map((node) => (
            <g key={node.node.entityId}>
              <circle
                cx={node.x}
                cy={node.y}
                r={node.radius}
                fill={
                  node.node.peakSeverity === null ? palette.muted : palette[node.node.peakSeverity]
                }
                stroke={pinnedEntityId === node.node.entityId ? palette.critical : 'transparent'}
                strokeWidth={2}
                className="cursor-pointer"
                role="button"
                tabIndex={0}
                aria-pressed={pinnedEntityId === node.node.entityId}
                aria-label={`Entity ${String(node.node.entityId)}, ${String(node.node.alerts)} alerts, ${String(node.node.records)} records`}
                onClick={() =>
                  onPin(pinnedEntityId === node.node.entityId ? null : node.node.entityId)
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onPin(pinnedEntityId === node.node.entityId ? null : node.node.entityId);
                  }
                }}
              >
                <title>
                  {`Entity ${String(node.node.entityId)} — ${String(node.node.records)} records in ${String(node.node.alerts)} alerts, peak ${node.node.peakSeverity ?? 'unrecognised'}`}
                </title>
              </circle>
              <text
                x={node.x}
                y={node.y + node.radius + 10}
                textAnchor="middle"
                fill={palette.muted}
                className="text-caption"
              >
                {node.node.entityId}
              </text>
            </g>
          ))}
        </svg>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-collapse text-caption">
            <caption className="sr-only">
              Ranked adjacency matrix of entity co-occurrence. Showing {matrix.axis.length} of{' '}
              {matrix.total} entities; empty cells mean no shared correlation trace.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="p-1 text-left font-semibold">
                  entity
                </th>
                {matrix.axis.map((column) => (
                  <th key={column.entityId} scope="col" className="p-1 font-semibold tabular-nums">
                    {column.entityId}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.axis.map((row) => (
                <tr key={row.entityId}>
                  <th scope="row" className="p-1 text-left font-normal tabular-nums text-ink">
                    {row.entityId}
                  </th>
                  {matrix.axis.map((column) => {
                    const cell = matrix.cells.find(
                      (candidate) =>
                        candidate.sourceId === row.entityId &&
                        candidate.targetId === column.entityId,
                    );
                    const weight = cell?.sharedTraces ?? 0;
                    return (
                      <td
                        key={column.entityId}
                        className="border border-line p-1 text-center tabular-nums"
                        style={{
                          // Shading is the only place a colour is computed, and it is
                          // an opacity on a token colour, never a literal.
                          backgroundColor: palette.high,
                          opacity:
                            row.entityId === column.entityId
                              ? 0
                              : 0.15 + 0.85 * (matrix.peak === 0 ? 0 : weight / matrix.peak),
                        }}
                        title={
                          weight === 0
                            ? `Entities ${String(row.entityId)} and ${String(column.entityId)}: no shared trace`
                            : `Entities ${String(row.entityId)} and ${String(column.entityId)}: ${String(weight)} shared traces`
                        }
                        data-testid={`cell-${String(row.entityId)}-${String(column.entityId)}`}
                      >
                        {row.entityId === column.entityId || weight === 0 ? '' : weight}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pinnedEntityId === null ? null : (
        <p className="mt-2 flex items-center gap-2 text-caption text-muted">
          <Badge tone="neutral">Pinned</Badge>
          Entity {pinnedEntityId} and its neighbours are shown; everything else is hidden.
        </p>
      )}
      {model.edges.length === 0 && model.nodes.length > 1 ? (
        <p className="mt-2 text-caption text-muted" data-testid="graph-no-edges">
          No shared correlation traces between these entities
          {` (last seen ${formatInstant(model.nodes[0]?.lastSeen ?? new Date().toISOString())}).`}
        </p>
      ) : null}
    </div>
  );
}
