/**
 * The entity graph (design.md §4.4), and the switch that replaces it at scale (T-418).
 *
 * §4.4 asks for two things in one breath: a force-directed graph, and a static fallback
 * "for >2,000 nodes (a force simulation at that size is unusable — we switch to a ranked
 * adjacency matrix **and say so**)". So this component has two renderers and no third
 * state, and the label is rendered with the mode rather than chosen by it:
 *
 *   * `force` — an SVG of circles and lines, node radius from the address's flow count
 *     (area-scaled, `graph.ts`), fill from its peak alert severity, edge width from the
 *     records that flowed between the two addresses. Hovering shows the numbers in a
 *     native `<title>`, and clicking a node pins it.
 *   * `adjacency` — a ranked matrix over the most active addresses, with the reason
 *     string and the "showing N of M" count rendered above it, because a matrix without
 *     that sentence looks like the whole graph.
 *
 * The layout is computed once per data change with a fixed tick count and no timer
 * (`layoutGraph`), so the picture is reproducible — and because it is never animated,
 * `reducedMotion` needs no flag here: there is no motion for a reader to opt out of.
 *
 * The node labels are **addresses**, because that is what the flow read model counts an
 * entity by (T-418): an alert's `entity_id` is not an address, so the graph names what
 * the traffic names, and the alert counts the endpoint attaches to an address are the
 * only numbers here that come from the alert side.
 */
import { useMemo } from 'react';

import { Badge, EmptyState } from '../../../components/ui';
import type { ChartPalette } from '../../../components/charts/palette';
import { formatCount, formatInstant } from '../../../lib/format';
import { adjacencyMatrix, layoutGraph, type GraphModel } from '../graph';

export interface EntityGraphProps {
  model: GraphModel;
  palette: ChartPalette;
  /** The pinned address, or `null`. Clicking a node toggles it. */
  pinnedId: string | null;
  onPin: (id: string | null) => void;
  width?: number;
  height?: number;
}

export function EntityGraph({
  model,
  palette,
  pinnedId,
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
        title="No addresses in this selection"
        description="Widen the brush or lower the flow threshold to bring addresses back into view."
      />
    );
  }

  return (
    <div>
      <p className="mb-2 text-caption text-muted">{model.reason}</p>

      {/* `group`, not `img`: the nodes are buttons, and a presentational `img` role
          would hide every one of them from assistive technology. */}
      {matrix === null ? (
        <svg
          role="group"
          aria-label={`Address relationships: ${String(model.nodes.length)} addresses, ${String(model.edges.length)} relationships. ${model.reason}`}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          className="w-full"
        >
          {layout.edges.map((edge) => (
            <line
              key={`${edge.edge.source}->${edge.edge.target}`}
              x1={edge.source.x}
              y1={edge.source.y}
              x2={edge.target.x}
              y2={edge.target.y}
              stroke={palette.grid}
              strokeWidth={Math.min(4, 0.5 + Math.log10(1 + edge.edge.flows) * 2)}
              data-testid={`edge-${edge.edge.source}-${edge.edge.target}`}
            />
          ))}

          {layout.nodes.map((node) => (
            <g key={node.node.id}>
              <circle
                cx={node.x}
                cy={node.y}
                r={node.radius}
                fill={
                  node.node.peakSeverity === null ? palette.muted : palette[node.node.peakSeverity]
                }
                stroke={pinnedId === node.node.id ? palette.critical : 'transparent'}
                strokeWidth={2}
                className="cursor-pointer"
                role="button"
                tabIndex={0}
                aria-pressed={pinnedId === node.node.id}
                aria-label={`Address ${node.node.id}, ${formatCount(node.node.flows)} flows, ${String(node.node.alerts)} alerts`}
                onClick={() => onPin(pinnedId === node.node.id ? null : node.node.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onPin(pinnedId === node.node.id ? null : node.node.id);
                  }
                }}
              >
                <title>
                  {`${node.node.id} — ${formatCount(node.node.flows)} flows (${formatCount(node.node.inbound)} in, ${formatCount(node.node.outbound)} out) in ${String(node.node.alerts)} alerts, peak ${node.node.peakSeverity ?? 'no alert'}`}
                </title>
              </circle>
              <text
                x={node.x}
                y={node.y + node.radius + 10}
                textAnchor="middle"
                fill={palette.muted}
                className="text-caption"
              >
                {node.node.id}
              </text>
            </g>
          ))}
        </svg>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-collapse text-caption">
            <caption className="sr-only">
              Ranked adjacency matrix of flow relationships. Showing {matrix.axis.length} of{' '}
              {matrix.total} addresses; empty cells mean no traffic in that direction.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="p-1 text-left font-semibold">
                  address
                </th>
                {matrix.axis.map((column) => (
                  <th key={column.id} scope="col" className="p-1 font-semibold tabular-nums">
                    {column.id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.axis.map((row) => (
                <tr key={row.id}>
                  <th scope="row" className="p-1 text-left font-normal tabular-nums text-ink">
                    {row.id}
                  </th>
                  {matrix.axis.map((column) => {
                    const cell = matrix.cells.find(
                      (candidate) =>
                        candidate.sourceId === row.id && candidate.targetId === column.id,
                    );
                    const weight = cell?.flows ?? 0;
                    return (
                      <td
                        key={column.id}
                        className="border border-line p-1 text-center tabular-nums"
                        style={{
                          // Shading is the only place a colour is computed, and it is
                          // an opacity on a token colour, never a literal.
                          backgroundColor: palette.high,
                          opacity:
                            row.id === column.id
                              ? 0
                              : 0.15 + 0.85 * (matrix.peak === 0 ? 0 : weight / matrix.peak),
                        }}
                        title={
                          weight === 0
                            ? `No traffic from ${row.id} to ${column.id} in this window`
                            : `${formatCount(weight)} flows from ${row.id} to ${column.id}`
                        }
                        data-testid={`cell-${row.id}-${column.id}`}
                      >
                        {row.id === column.id || weight === 0 ? '' : weight}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pinnedId === null ? null : (
        <p className="mt-2 flex items-center gap-2 text-caption text-muted">
          <Badge tone="neutral">Pinned</Badge>
          {pinnedId} and its neighbours are shown; everything else is hidden.
        </p>
      )}
      {model.edges.length === 0 && model.nodes.length > 1 ? (
        <p className="mt-2 text-caption text-muted" data-testid="graph-no-edges">
          No flow relationships between these addresses
          {` (last seen ${formatInstant(model.nodes[0]?.lastSeen ?? new Date().toISOString())}).`}
        </p>
      ) : null}
    </div>
  );
}
