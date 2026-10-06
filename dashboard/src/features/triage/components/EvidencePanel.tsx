/**
 * Zone 3 — "Raw evidence" (design.md §4.3).
 *
 * Three tabs, because the design has three: the windows each model scored, and the
 * other alerts on the same entity around this one. What the API returns is a trail
 * of *pointers* — window id, modality, score, model, when it closed — not the raw
 * flows and log lines themselves, which live in the stream store under FR-05's
 * retention. So the panel shows the trail, and says where the records themselves
 * are: a table of invented columns would be the one thing this screen cannot do.
 *
 * Two states are explicit, and both are acceptance criteria:
 *
 *   * **`evidence expired at <date>`** — computed by the read model from the
 *     retention policy and rendered here verbatim, because an analyst deciding
 *     whether they can re-check the alert needs the date, not an adjective. The
 *     trail keeps rendering underneath: the *pointers* survive, the raw records do
 *     not, and the difference is the whole reason the panel says which is which.
 *   * **unreadable entries** — a trail with entries that could not be decoded says
 *     how many. A silently shorter trail looks complete, which is the failure mode
 *     of every "skip the bad rows" implementation.
 *
 * The tabs are the ARIA pattern, arrow keys included: a tablist that can only be
 * driven by Tab and Space is a tablist that fights the keyboard, and this screen's
 * acceptance criterion is that the whole loop works without a mouse.
 */
import { useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';

import { Card, DataTable, EmptyState, type Column } from '../../../components/ui';
import { formatCount, formatInstant, formatStamp } from '../../../lib/format';
import { alertHref } from '../links';
import type { AlertDetail, EvidenceOccurrence } from '../types';
import { evidenceView, relatedView } from '../view';

/** A tab is a modality, or the related alerts beside this one. */
interface Tab {
  id: string;
  label: string;
  count: number;
}

const OCCURRENCE_COLUMNS: readonly Column<EvidenceOccurrence>[] = [
  {
    id: 'at',
    header: 'Window closed',
    cell: (row) => <span className="font-mono">{formatInstant(row.at)}</span>,
    sortValue: (row) => row.at,
  },
  {
    id: 'modality',
    header: 'Modality',
    cell: (row) => row.modality,
    sortValue: (row) => row.modality,
  },
  {
    id: 'score',
    header: 'Score',
    cell: (row) => <span className="font-mono">{row.score.toFixed(3)}</span>,
    sortValue: (row) => row.score,
  },
  {
    id: 'model',
    header: 'Model',
    cell: (row) => <span className="font-mono">{row.model ?? 'not recorded'}</span>,
    sortValue: (row) => row.model ?? '',
  },
  {
    id: 'expires',
    header: 'Raw records expire',
    cell: (row) => (
      <span className="font-mono">
        {row.expired ? `expired ${formatStamp(row.expires_at)}` : formatStamp(row.expires_at)}
      </span>
    ),
    sortValue: (row) => row.expires_at,
  },
];

const MODALITY_LABELS: Record<string, string> = { flow: 'Flows', log: 'Log lines' };

export function EvidencePanel({ detail }: { detail: AlertDetail }) {
  const view = evidenceView(detail.evidence);
  const related = relatedView(detail.related);
  const tabs: Tab[] = [
    ...view.counts.map((entry) => ({
      id: entry.modality,
      label: MODALITY_LABELS[entry.modality] ?? entry.modality,
      count: entry.count,
    })),
    { id: 'related', label: 'Related alerts', count: related.items.length },
  ];
  const [selected, setSelected] = useState<string>(tabs[0]?.id ?? 'related');
  const active = tabs.find((tab) => tab.id === selected) ?? tabs[0]!;

  /** Left/right arrows move along the tablist, as the ARIA pattern expects. */
  const onTabKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    const index = tabs.findIndex((tab) => tab.id === active.id);
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = tabs[(index + step + tabs.length) % tabs.length];
    if (next === undefined) return;
    event.preventDefault();
    setSelected(next.id);
    document.getElementById(`evidence-tab-${next.id}`)?.focus();
  };

  const occurrences = view.occurrences.filter(
    (occurrence) => active.id !== 'related' && occurrence.modality === active.id,
  );

  return (
    <Card title="Raw evidence">
      {view.expiredLine === null ? (
        <p className="text-body-sm text-muted">
          Raw records behind this alert are kept for {formatCount(view.retentionDays)} d and were
          still inside that window when this page loaded.
        </p>
      ) : (
        <p role="status" className="text-body-sm font-semibold text-severityText-medium">
          {view.expiredLine}
        </p>
      )}

      <div
        role="tablist"
        aria-label="Evidence"
        onKeyDown={onTabKeys}
        // `-1` rather than `0`: the tabs below carry the tab order (roving, so
        // only the selected one is a Tab stop), and this container is focusable
        // only so a key handler on an interactive role has somewhere to live.
        tabIndex={-1}
        className="mt-3 flex flex-wrap gap-2"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            type="button"
            id={`evidence-tab-${tab.id}`}
            aria-selected={tab.id === active.id}
            aria-controls={`evidence-panel-${tab.id}`}
            tabIndex={tab.id === active.id ? 0 : -1}
            onClick={() => setSelected(tab.id)}
            className="rounded-input border border-line px-3 py-1 text-body-sm text-ink aria-selected:border-accent"
          >
            {tab.label} {formatCount(tab.count)}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`evidence-panel-${active.id}`}
        aria-labelledby={`evidence-tab-${active.id}`}
        className="mt-3"
      >
        {active.id === 'related' ? (
          related.items.length === 0 ? (
            <EmptyState
              title="No related alerts"
              description={`No other alert on this entity within ±${String(
                related.windowMinutes,
              )} min of this one.`}
            />
          ) : (
            <>
              <ul className="flex flex-col gap-2">
                {related.items.map((row) => (
                  <li key={`${String(row.id)}-${row.created_at}`}>
                    <Link className="underline" to={alertHref(row)}>
                      <span className="font-mono">{formatInstant(row.created_at)}</span> ·{' '}
                      {row.family} · score {row.score.toFixed(2)}
                    </Link>
                  </li>
                ))}
              </ul>
              {related.truncated ? (
                <p className="mt-2 text-body-sm text-muted">
                  Showing the nearest {String(related.items.length)}; more related alerts exist.
                </p>
              ) : null}
            </>
          )
        ) : occurrences.length === 0 ? (
          <EmptyState
            title={`No ${active.label.toLowerCase()} windows`}
            description="The alert's trail carries no window for this modality."
          />
        ) : (
          <DataTable
            caption={`Evidence windows scored as ${active.label.toLowerCase()}`}
            columns={OCCURRENCE_COLUMNS}
            rows={occurrences}
            rowKey={(row) => row.id}
            height={220}
          />
        )}
      </div>

      {view.unreadable === 0 ? null : (
        <p role="status" className="mt-3 text-body-sm text-severityText-medium">
          {formatCount(view.unreadable)} trail {view.unreadable === 1 ? 'entry' : 'entries'} could
          not be read and are not shown.
        </p>
      )}
      {view.note === null ? null : <p className="mt-2 text-body-sm text-muted">{view.note}</p>}
      <p className="mt-2 text-body-sm text-muted">
        Window {view.windowLabel}
        {view.traceId === null ? null : (
          <>
            {' '}
            · trace <span className="font-mono">{view.traceId}</span>
          </>
        )}
        {view.grouped ? ' · grouped case (several detections fused)' : ''}
      </p>
    </Card>
  );
}
