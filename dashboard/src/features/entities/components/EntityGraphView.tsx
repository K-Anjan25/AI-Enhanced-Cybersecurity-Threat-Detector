import React, { useCallback, useEffect, useState } from "react";
import EntityApi from "../../../api/entityApi";
import type { EntityGraphResponse, ThreatEntity } from "../../../types/entity";

interface Props {
  root: ThreatEntity;
  onPivot: (entity: ThreatEntity) => void;
  onClose: () => void;
}

const WIDTH = 760;
const HEIGHT = 560;
const CENTER_X = WIDTH / 2;
const CENTER_Y = HEIGHT / 2;
const RING_SPACING = 120;
const MAX_DEPTH = 4;

const typeColor: Record<string, string> = {
  ip: "#22d3ee",
  domain: "#fbbf24",
  hash: "#a78bfa",
  email: "#34d399",
  file: "#f87171",
};

const typeLabel: Record<string, string> = {
  ip: "IP",
  domain: "Domain",
  hash: "Hash",
  email: "Email",
  file: "File",
};

const typeFill: Record<string, string> = {
  ip: "rgba(34,211,238,0.15)",
  domain: "rgba(251,191,36,0.15)",
  hash: "rgba(167,139,250,0.15)",
  email: "rgba(52,211,153,0.15)",
  file: "rgba(248,113,113,0.15)",
};

interface Positioned {
  x: number;
  y: number;
  depth: number;
}

const EntityGraphView: React.FC<Props> = ({ root, onPivot, onClose }) => {
  const [graph, setGraph] = useState<EntityGraphResponse | null>(null);
  const [depth, setDepth] = useState(2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await EntityApi.fetchEntityGraph(root.id, depth);
      setGraph(data);
    } catch (err: any) {
      setError(err?.detail || "Failed to load attack graph");
    } finally {
      setLoading(false);
    }
  }, [root.id, depth]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const layout = (): { positions: Map<number, Positioned>; edges: Array<{ source: number; target: number; relation: string }> } => {
    const positions = new Map<number, Positioned>();
    const edges = graph?.links || [];
    const nodes = graph?.nodes || [];

    if (!nodes.length) {
      return { positions, edges };
    }

    const adj = new Map<number, number[]>();
    edges.forEach((edge) => {
      if (!adj.has(edge.source)) adj.set(edge.source, []);
      adj.get(edge.source)!.push(edge.target);
    });

    const depths = new Map<number, number>([[root.id, 0]]);
    const queue = [root.id];
    while (queue.length) {
      const current = queue.shift()!;
      const currentDepth = depths.get(current) ?? 0;
      for (const child of adj.get(current) || []) {
        if (depths.has(child)) continue;
        depths.set(child, currentDepth + 1);
        queue.push(child);
      }
    }

    const byDepth = new Map<number, number[]>();
    for (const [id, level] of depths.entries()) {
      if (!byDepth.has(level)) byDepth.set(level, []);
      byDepth.get(level)!.push(id);
    }

    for (const [level, ids] of byDepth.entries()) {
      const count = ids.length;
      const radius = level * RING_SPACING;
      ids.forEach((id, index) => {
        const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
        positions.set(id, {
          x: CENTER_X + radius * Math.cos(angle),
          y: CENTER_Y + radius * Math.sin(angle),
          depth: level,
        });
      });
    }

    return { positions, edges };
  };

  const nodeById = new Map<number, ThreatEntity>((graph?.nodes || []).map((n) => [n.id, n]));
  const { positions, edges } = layout();

  const nodeRadius = (entity: ThreatEntity): number => {
    const base = 10;
    const scale = Math.min(entity.risk_score / 100, 1) * 6;
    return Math.max(base, Math.min(base + scale, 18));
  };

  const drawEdges = () => {
    return edges.map((edge, index) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return null;
      return (
        <line
          key={index}
          x1={source.x}
          y1={source.y}
          x2={target.x}
          y2={target.y}
          stroke="#475569"
          strokeWidth={1.25}
          strokeDasharray={edge.relation === "communicates" ? "0" : "4 4"}
          opacity={0.7}
        >
          <title>{`${edge.relation} (depth ${target.depth})`}</title>
        </line>
      );
    });
  };

  const drawNodes = () => {
    return Array.from(positions.entries()).map(([id, pos]) => {
      const entity = nodeById.get(id);
      if (!entity) return null;
      const r = nodeRadius(entity);
      const color = typeColor[entity.entity_type] || "#94a3b8";
      const isRoot = id === root.id;
      return (
        <g
          key={id}
          transform={`translate(${pos.x}, ${pos.y})`}
          className="cursor-pointer"
          onClick={() => {
            if (!isRoot) onPivot(entity);
          }}
        >
          <circle
            r={isRoot ? r + 6 : r}
            fill={typeFill[entity.entity_type] || "rgba(148,163,184,0.15)"}
            stroke={color}
            strokeWidth={isRoot ? 3 : 2}
          />
          {isRoot && (
            <circle r={r + 9} fill="none" stroke={color} strokeWidth={1} opacity={0.4} strokeDasharray="3 3" />
          )}
          <text y={r + 16} textAnchor="middle" className="fill-content-secondary font-mono" fontSize={10}>
            {entity.value.length > 18 ? `${entity.value.slice(0, 16)}...` : entity.value}
          </text>
          <text y={-r - 6} textAnchor="middle" fontSize={9} fill={color} className="font-semibold uppercase tracking-wider">
            {isRoot ? `Root · ${typeLabel[entity.entity_type]}` : typeLabel[entity.entity_type]}
          </text>
          <title>{`${typeLabel[entity.entity_type]}: ${entity.value}\nRisk: ${entity.risk_score.toFixed(1)}\nOccurrences: ${entity.occurrences}`}</title>
        </g>
      );
    });
  };

  const legend = [
    { type: "ip", label: "IP address" },
    { type: "domain", label: "Domain" },
    { type: "hash", label: "File hash" },
    { type: "email", label: "Email" },
    { type: "file", label: "File" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-app-surface w-full max-w-4xl rounded-xl p-6 shadow-2xl border border-line-subtle max-h-[92vh] flex flex-col">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-content-primary truncate">Attack graph: {root.value}</h3>
            <p className="text-sm text-content-secondary mt-0.5">
              Click a node to pivot; relationships are directional.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label htmlFor="graph-depth" className="text-xs font-medium text-content-secondary">
              Depth
            </label>
            <select
              id="graph-depth"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="px-2.5 py-1.5 bg-app-bg border border-line-subtle rounded-lg text-xs text-content-primary focus:outline-none focus:border-accent-primary transition cursor-pointer"
            >
              {[1, 2, 3, 4].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg bg-app-subtle hover:bg-line-bright border border-line-subtle text-xs font-medium text-content-secondary transition"
            >
              Close
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-4 mb-3">
          {legend.map((item) => (
            <span key={item.type} className="inline-flex items-center gap-1.5 text-xs text-content-secondary">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: typeColor[item.type] }}
              />
              {item.label}
            </span>
          ))}
        </div>

        <div className="relative flex-1 min-h-[400px] bg-app-bg rounded-lg border border-line-subtle overflow-auto">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center text-content-tertiary text-sm">
              Loading graph...
            </div>
          ) : error ? (
            <div className="absolute inset-0 flex items-center justify-center px-6 text-sm text-red-400 text-center">
              {error}
            </div>
          ) : graph && graph.nodes.length > 0 ? (
            <svg
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              width="100%"
              height="100%"
              role="img"
              aria-label={`Attack graph for entity ${root.value}`}
            >
              <rect width={WIDTH} height={HEIGHT} fill="transparent" />
              {drawEdges()}
              {drawNodes()}
            </svg>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-content-tertiary text-sm">
              No connected entities found for this indicator.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EntityGraphView;