import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, X, ZoomIn, ZoomOut } from "lucide-react";
import EntityApi from "../../../api/entityApi";
import { getApiError } from "../../../utils/getApiError";
import { useHotkey } from "../../../hooks";
import type { EntityGraphResponse, ThreatEntity } from "../../../types/entity";
import { Select } from "../../../components/ui/Select";

interface Props {
  root: ThreatEntity;
  onPivot: (entity: ThreatEntity) => void;
  onClose: () => void;
}

const WIDTH = 980;
const HEIGHT = 620;
const CENTER_X = WIDTH / 2;
const CENTER_Y = HEIGHT / 2;
const RING_SPACING = 110;
const MAX_DEPTH = 4;

const typeColor: Record<string, string> = {
  ip: "#e5a54b",
  domain: "#e77a8b",
  hash: "#7e87a3",
  email: "#4fb8a8",
  file: "#f26d6d",
  account: "#8b7cf6",
  host: "#9d7cff",
};

const typeLabel: Record<string, string> = {
  ip: "IP",
  domain: "Domain",
  hash: "Hash",
  email: "Email",
  file: "File",
  account: "Account",
  host: "Host",
};

const typeFill: Record<string, string> = {
  ip: "rgba(245,158,11,0.15)",
  domain: "rgba(233,196,106,0.15)",
  hash: "rgba(201,173,167,0.15)",
  email: "rgba(132,169,140,0.15)",
  file: "rgba(231,111,81,0.15)",
  account: "rgba(37,99,235,0.15)",
  host: "rgba(114,134,211,0.15)",
};

const LEGEND_TYPES = [
  { type: "ip", label: "IP address" },
  { type: "domain", label: "Domain" },
  { type: "hash", label: "File hash" },
  { type: "email", label: "Email" },
  { type: "file", label: "File" },
  { type: "account", label: "Account" },
  { type: "host", label: "Host / asset" },
];

interface Positioned {
  x: number;
  y: number;
  depth: number;
}

const riskTone = (score: number): string => {
  if (score >= 0.75) return "text-status-critical";
  if (score >= 0.5) return "text-status-warning";
  if (score >= 0.25) return "text-chart-4";
  return "text-status-success";
};

const riskBar = (score: number): string => {
  if (score >= 0.75) return "#f26d6d";
  if (score >= 0.5) return "#f0824f";
  if (score >= 0.25) return "#e5a54b";
  return "#52b788";
};

const EntityGraphView: React.FC<Props> = ({ root, onPivot, onClose }) => {
  const [graph, setGraph] = useState<EntityGraphResponse | null>(null);
  const [depth, setDepth] = useState(2);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Interaction state
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startY: number; viewX: number; viewY: number; moved: boolean } | null>(null);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await EntityApi.fetchEntityGraph(root.id, depth);
      setGraph(data);
      setSelectedId(null);
      setHoveredId(null);
    } catch (err: any) {
      setError(getApiError(err, "Failed to load attack graph"));
    } finally {
      setLoading(false);
    }
  }, [root.id, depth]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // Escape closes the modal.
  useHotkey("escape", onClose);

  // Wheel-to-zoom (non-passive listener so preventDefault works).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setView((v) => {
        const factor = e.deltaY < 0 ? 1.18 : 0.85;
        const scale = Math.min(3.5, Math.max(0.4, v.scale * factor));
        const rect = el.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const k = scale / v.scale;
        return { scale, x: mx - (mx - v.x) * k, y: my - (my - v.y) * k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (factor: number) => {
    setView((v) => {
      const scale = Math.min(3.5, Math.max(0.4, v.scale * factor));
      const k = scale / v.scale;
      return { scale, x: CENTER_X - (CENTER_X - v.x) * k, y: CENTER_Y - (CENTER_Y - v.y) * k };
    });
  };

  const resetView = () => setView({ x: 0, y: 0, scale: 1 });

  // Drag-to-pan
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, viewX: view.x, viewY: view.y, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
    if (d.moved) setView((v) => ({ ...v, x: d.viewX + dx, y: d.viewY + dy }));
  };
  const onPointerUp = () => {
    dragRef.current = null;
  };

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  /* ------------------------------- layout ------------------------------- */
  const layout = (): {
    positions: Map<number, Positioned>;
    edges: Array<{ source: number; target: number; relation: string }>;
  } => {
    const positions = new Map<number, Positioned>();
    const edges = graph?.links || [];
    const nodes = graph?.nodes || [];
    if (!nodes.length) return { positions, edges };

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

  // Neighbours map for highlighting + the details panel.
  const adjacency = useMemo(() => {
    const map = new Map<number, Array<{ id: number; relation: string }>>();
    (graph?.links || []).forEach((ed) => {
      if (!map.has(ed.source)) map.set(ed.source, []);
      map.get(ed.source)!.push({ id: ed.target, relation: ed.relation });
      if (!map.has(ed.target)) map.set(ed.target, []);
      map.get(ed.target)!.push({ id: ed.source, relation: ed.relation });
    });
    return map;
  }, [graph?.links]);

  const highlightSet = useMemo(() => {
    const focus = hoveredId ?? selectedId;
    if (focus === null || focus === undefined) return null; // null = everything lit
    const set = new Set<number>([focus]);
    (adjacency.get(focus) || []).forEach((n) => set.add(n.id));
    return set;
  }, [hoveredId, selectedId, adjacency]);

  const isHighlighted = (id: number): boolean => highlightSet === null || highlightSet.has(id);

  const nodeRadius = (entity: ThreatEntity): number => {
    const base = 10;
    const scale = Math.min(Number(entity.risk_score) || 0, 1) * 6;
    return Math.max(base, Math.min(base + scale, 18));
  };

  const selected = selectedId !== null ? nodeById.get(selectedId) ?? null : null;
  const hovered = hoveredId !== null ? nodeById.get(hoveredId) ?? null : null;

  const drawEdges = () =>
    edges.map((edge, index) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return null;
      const lit = isHighlighted(edge.source) && isHighlighted(edge.target);
      const isFocusedEdge = (hoveredId !== null && (edge.source === hoveredId || edge.target === hoveredId)) ||
        (selectedId !== null && (edge.source === selectedId || edge.target === selectedId));
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      return (
        <g key={index} opacity={lit ? (isFocusedEdge ? 1 : 0.75) : 0.12} className="transition-opacity">
          <line
            x1={source.x}
            y1={source.y}
            x2={target.x}
            y2={target.y}
            stroke="rgb(var(--c-line-bright))"
            strokeWidth={isFocusedEdge ? 2 : 1.25}
            strokeDasharray={edge.relation === "communicates" ? "0" : "4 4"}
          >
            <title>{`${edge.relation}`}</title>
          </line>
          {isFocusedEdge && (
            <text
              x={midX}
              y={midY - 5}
              textAnchor="middle"
              fontSize={9}
              fill="rgb(var(--c-content-tertiary))"
              className="select-none"
            >
              {edge.relation}
            </text>
          )}
        </g>
      );
    });

  const handleNodeClick = (e: React.MouseEvent, entity: ThreatEntity) => {
    if (dragRef.current?.moved) return;
    e.stopPropagation();
    setSelectedId(entity.id);
    setHoveredId(null);
  };

  const handleNodeDblClick = (e: React.MouseEvent, entity: ThreatEntity) => {
    if (dragRef.current?.moved) return;
    if (entity.id === root.id) return;
    onPivot(entity);
  };

  const drawNodes = () =>
    Array.from(positions.entries()).map(([id, pos]) => {
      const entity = nodeById.get(id);
      if (!entity) return null;
      const r = nodeRadius(entity);
      const color = typeColor[entity.entity_type] || "#a1a1aa";
      const isRoot = id === root.id;
      const lit = isHighlighted(id);
      const isSelected = id === selectedId;
      const degree = (adjacency.get(id) || []).length;
      return (
        <g
          key={id}
          transform={`translate(${pos.x}, ${pos.y})`}
          className="cursor-pointer"
          opacity={lit ? 1 : 0.22}
          onClick={(e) => handleNodeClick(e, entity)}
          onDoubleClick={(e) => handleNodeDblClick(e, entity)}
          onMouseEnter={() => {
            setHoveredId(id);
            setTooltipPos(null);
          }}
          onMouseLeave={() => setHoveredId(null)}
        >
          <circle
            r={isRoot ? r + 6 : r}
            fill={typeFill[entity.entity_type] || "rgba(161,161,170,0.15)"}
            stroke={color}
            strokeWidth={isRoot ? 3 : isSelected ? 3 : 2}
          />
          {isRoot && (
            <circle r={r + 9} fill="none" stroke={color} strokeWidth={1} opacity={0.4} strokeDasharray="3 3" />
          )}
          {isSelected && (
            <circle r={r + 5} fill="none" stroke={color} strokeWidth={1.5} opacity={0.9} />
          )}
          <text y={r + 16} textAnchor="middle" className="fill-content-secondary font-mono" fontSize={10} pointerEvents="none">
            {entity.value.length > 18 ? `${entity.value.slice(0, 16)}...` : entity.value}
          </text>
          <text y={-r - 6} textAnchor="middle" fontSize={9} fill={color} className="font-semibold uppercase tracking-wider" pointerEvents="none">
            {isRoot ? `Root · ${typeLabel[entity.entity_type]}` : typeLabel[entity.entity_type]}
          </text>
          <title>{`${typeLabel[entity.entity_type]}: ${entity.value}\nRisk: ${(Number(entity.risk_score) || 0).toFixed(2)}\nOccurrences: ${entity.occurrences ?? 0}\nDegree: ${degree}`}</title>
        </g>
      );
    });

  const tooltipEntity = hovered;
  const tooltipVisible = tooltipEntity && tooltipPos;

  /* --------------------------- details panel ---------------------------- */
  const detailsEntity = selected ?? null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-app-surface w-full max-w-5xl rounded-2xl p-6 shadow-2xl border border-line-subtle max-h-[94vh] flex flex-col">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-content-primary truncate">Attack graph: {root.value}</h3>
            <p className="text-sm text-content-secondary mt-0.5">
              {graph ? `${graph.nodes.length} nodes · ${graph.links.length} edges · depth ${depth}` : "Loading…"} — scroll to zoom, drag to pan, click to inspect, double-click to pivot.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <label htmlFor="graph-depth" className="text-xs font-medium text-content-secondary">
              Depth
            </label>
            <Select
              inline
              id="graph-depth"
              value={String(depth)}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-auto px-2.5 py-1.5 rounded-lg text-xs"
              options={[1, 2, 3, 4].map((d) => ({ value: String(d), label: String(d) }))}
            />
            <div className="flex items-center gap-1 p-1 rounded-full bg-app-subtle border border-line-subtle">
              <button
                type="button"
                onClick={() => zoomBy(1.25)}
                title="Zoom in"
                aria-label="Zoom in"
                className="w-6 h-6 flex items-center justify-center rounded-full text-content-secondary hover:text-content-primary transition"
              >
                <ZoomIn size={14} />
              </button>
              <button
                type="button"
                onClick={() => zoomBy(0.8)}
                title="Zoom out"
                aria-label="Zoom out"
                className="w-6 h-6 flex items-center justify-center rounded-full text-content-secondary hover:text-content-primary transition"
              >
                <ZoomOut size={14} />
              </button>
              <button
                type="button"
                onClick={resetView}
                title="Reset view"
                aria-label="Reset view"
                className="w-6 h-6 flex items-center justify-center rounded-full text-content-secondary hover:text-content-primary transition"
              >
                <Maximize2 size={13} />
              </button>
              <span className="text-[10px] font-mono text-content-tertiary w-8 text-center tabular-nums">
                {Math.round(view.scale * 100)}%
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close graph"
              className="w-8 h-8 flex items-center justify-center rounded-full bg-app-subtle hover:bg-line-bright border border-line-subtle text-content-secondary transition"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-3">
          {LEGEND_TYPES.map((item) => (
            <span key={item.type} className="inline-flex items-center gap-1.5 text-xs text-content-secondary">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: typeColor[item.type] }} />
              {item.label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5 text-xs text-content-tertiary">
            <span className="w-3 border-t border-line-bright" /> communicates
          </span>
          <span className="inline-flex items-center gap-1.5 text-xs text-content-tertiary">
            <span className="w-3 border-t border-dashed border-line-bright" /> other relation
          </span>
        </div>

        <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
          <div
            ref={containerRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onMouseMove={onMouseMove}
            className="relative flex-1 min-h-[360px] lg:min-h-0 bg-app-bg rounded-lg border border-line-subtle overflow-hidden touch-none cursor-grab active:cursor-grabbing"
          >
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center text-content-tertiary text-sm">
                Loading graph…
              </div>
            ) : error ? (
              <div className="absolute inset-0 flex items-center justify-center px-6 text-sm text-status-critical text-center">
                {error}
              </div>
            ) : graph && graph.nodes.length > 0 ? (
              <svg
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                width="100%"
                height="100%"
                preserveAspectRatio="xMidYMid meet"
                role="img"
                aria-label={`Attack graph for entity ${root.value}`}
                className="block"
              >
                <rect width={WIDTH} height={HEIGHT} fill="transparent" />
                <g transform={`translate(${view.x}, ${view.y}) scale(${view.scale})`}>
                  {drawEdges()}
                  {drawNodes()}
                </g>
              </svg>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-content-tertiary text-sm">
                No connected entities found for this indicator.
              </div>
            )}

            {tooltipVisible && tooltipEntity && (
              <div
                className="pointer-events-none absolute z-10 w-56 rounded-xl border border-line-bright bg-app-surface px-3 py-2 shadow-overlay text-xs"
                style={{
                  left: Math.min(Math.max(tooltipPos!.x + 14, 8), (containerRef.current?.clientWidth || 300) - 236),
                  top: Math.min(Math.max(tooltipPos!.y + 14, 8), (containerRef.current?.clientHeight || 300) - 120),
                }}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: typeColor[tooltipEntity.entity_type] || "#a1a1aa" }}>
                    {typeLabel[tooltipEntity.entity_type] || tooltipEntity.entity_type}
                  </span>
                  <span className={`font-mono font-semibold ${riskTone(Number(tooltipEntity.risk_score) || 0)}`}>
                    {(Number(tooltipEntity.risk_score) || 0).toFixed(2)}
                  </span>
                </div>
                <p className="font-mono text-content-primary break-words leading-snug">{tooltipEntity.value}</p>
                <p className="text-content-tertiary mt-1">
                  {tooltipEntity.occurrences ?? 0} occurrence{tooltipEntity.occurrences === 1 ? "" : "s"} ·{" "}
                  {(adjacency.get(tooltipEntity.id) || []).length} connection{(adjacency.get(tooltipEntity.id) || []).length === 1 ? "" : "s"}
                </p>
              </div>
            )}
          </div>

          {/* Details panel */}
          <aside className="w-full lg:w-64 shrink-0 flex flex-col gap-3 overflow-y-auto max-h-56 lg:max-h-full">
            {detailsEntity ? (
              <>
                <div className="rounded-xl border border-line-subtle bg-app-bg p-3">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: typeColor[detailsEntity.entity_type] || "#a1a1aa" }}>
                      {typeLabel[detailsEntity.entity_type] || detailsEntity.entity_type}
                      {detailsEntity.id === root.id && <span className="ml-1.5 text-content-tertiary">· root</span>}
                    </span>
                    <span className={`font-mono text-sm font-bold tabular-nums ${riskTone(Number(detailsEntity.risk_score) || 0)}`}>
                      {(Number(detailsEntity.risk_score) || 0).toFixed(2)}
                    </span>
                  </div>
                  <p className="font-mono text-xs text-content-primary break-words leading-snug">{detailsEntity.value}</p>
                  <div className="h-1.5 bg-app-subtle rounded-full mt-2 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${Math.min((Number(detailsEntity.risk_score) || 0) * 100, 100)}%`, backgroundColor: riskBar(Number(detailsEntity.risk_score) || 0) }}
                    />
                  </div>
                  <dl className="mt-2 space-y-1 text-[11px] text-content-tertiary">
                    <div className="flex justify-between">
                      <dt>Occurrences</dt>
                      <dd className="font-mono text-content-primary">{detailsEntity.occurrences ?? 0}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="shrink-0">Last seen</dt>
                      <dd className="font-mono text-content-primary truncate">
                        {detailsEntity.last_seen ? new Date(detailsEntity.last_seen).toLocaleString() : "—"}
                      </dd>
                    </div>
                  </dl>
                  {detailsEntity.id !== root.id && (
                    <button
                      type="button"
                      onClick={() => onPivot(detailsEntity)}
                      className="mt-3 w-full px-3 py-1.5 rounded-full bg-brand-gradient text-brand-ink text-xs font-semibold hover:opacity-90 transition"
                    >
                      Pivot to this node
                    </button>
                  )}
                </div>

                <div>
                  <h4 className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary mb-1.5">
                    Connections ({(adjacency.get(detailsEntity.id) || []).length})
                  </h4>
                  {adjacency.get(detailsEntity.id)?.length ? (
                    <ul className="space-y-1">
                      {adjacency.get(detailsEntity.id)!.map((n) => {
                        const nb = nodeById.get(n.id);
                        if (!nb) return null;
                        return (
                          <li key={n.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedId(nb.id)}
                              className="w-full text-left rounded-lg border border-line-subtle bg-app-bg hover:bg-line-bright/40 transition px-2.5 py-1.5"
                            >
                              <span className="flex items-center gap-1.5 text-[11px]">
                                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: typeColor[nb.entity_type] || "#a1a1aa" }} />
                                <span className="font-mono text-content-primary truncate">{nb.value}</span>
                              </span>
                              <span className="block text-[10px] text-content-tertiary mt-0.5">
                                {typeLabel[nb.entity_type]} · {n.relation} · risk {((Number(nb.risk_score) || 0) * 100).toFixed(0)}%
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-xs text-content-tertiary">No direct connections.</p>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-line-bright bg-app-bg p-4 text-xs text-content-tertiary leading-relaxed">
                <p className="font-semibold text-content-secondary mb-1">Inspect a node</p>
                Click any node to see its details and connections here. Scroll to zoom,
                drag to pan, double-click a node to pivot the graph to it.
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
};

export default EntityGraphView;
