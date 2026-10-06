/**
 * Thresholds — design.md §4.8: "value, source (`default|calibrated|manual`), last
 * changed by/at, and a preview of the alert-count impact over the last 7 days before
 * saving" (FR-18, FR-32, R-69).
 *
 * The preview is the reason this panel is a dialog rather than an inline field: the
 * operator types a value, **reads what it would have done to the recorded alerts**,
 * and only then saves. `GET /api/v1/thresholds/preview` does the counting, so the
 * number on screen is the same number the server would have produced, not an
 * estimate the dashboard made up out of a chart.
 *
 * Two things the panel refuses to imply:
 *
 *   * **A preview is about the past.** The band table's sentence names the window and
 *     the unit — alert rows, not occurrences (the correlator groups repeats before it
 *     bands one, T-308) — and says when the walk hit its page cap, because a floored
 *     count presented as a total is the most misleading number a preview can show.
 *   * **`info` has no bound.** Every band's value is a *lower* bound, and `info` is
 *     the bucket everything above the last one falls into; there is nothing to set,
 *     and the row says so rather than offering a control the server would refuse.
 */
import { useState } from 'react';

import { Badge, Button, Card, Modal, useToast } from '../../../components/ui';
import {
  thresholdRefusalMessage,
  useRecalibrate,
  useSetThreshold,
  useThresholdPreview,
  useThresholds,
} from '../hooks';
import {
  BAND_WITHOUT_BOUND,
  bandRows,
  formatThreshold,
  knownFamilies,
  readPreview,
  setReadiness,
  type BandRow,
} from '../thresholds';

/** The families the panel offers when the deployment has moved none. */
const DEFAULT_FAMILIES: readonly string[] = ['flow', 'log', 'auth'];

export function ThresholdsPanel() {
  const thresholds = useThresholds();
  const set = useSetThreshold();
  const recalibrate = useRecalibrate();
  const toast = useToast();
  const [family, setFamily] = useState<string | null>(null);
  const [editing, setEditing] = useState<BandRow | null>(null);

  const moved = knownFamilies(thresholds.data);
  const families = [...new Set([...moved, ...DEFAULT_FAMILIES])].sort();
  // Open on a family this deployment has actually moved: the interesting rows are the
  // ones somebody chose, and FR-13's defaults are visible either way.
  const active = family ?? moved[0] ?? families[0] ?? null;
  const rows = active === null ? [] : bandRows(thresholds.data, active);

  if (thresholds.isPending) {
    return <Card title="Thresholds" state="loading" loadingLines={6} />;
  }
  if (thresholds.isError) {
    return (
      <Card
        title="Thresholds"
        state="error"
        error={{
          message: 'The thresholds could not be read',
          detail:
            'Nothing is shown rather than FR-13\u2019s defaults alone: a default presented as the value in force would be a claim about this deployment that the read failed to make.',
        }}
      />
    );
  }

  return (
    <Card
      title="Thresholds"
      actions={
        <div className="flex items-center gap-2">
          <label className="text-body-sm text-muted" htmlFor="threshold-family">
            Family
          </label>
          <select
            id="threshold-family"
            className="rounded-control border border-line bg-base px-2 py-1 text-body-sm"
            value={active ?? ''}
            onChange={(event) => {
              setFamily(event.target.value);
            }}
          >
            {families.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="secondary"
            loading={recalibrate.isPending}
            onClick={() => {
              recalibrate.mutate('high', {
                onSuccess: (result) => {
                  toast(
                    'success',
                    `Recalibration ran over ${String(result.window_days)} days: ${String(result.changed)} of ${String(result.considered)} bands moved.`,
                  );
                },
              });
            }}
          >
            Recalibrate now
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-body-sm text-muted">
          Each value is the lower bound of its band: a score at or above it is banded at least this
          severely, and bands are matched from the top down. A hand-set value must keep the order
          intact, and the server refuses one that would not.
        </p>
        {recalibrate.isError ? (
          <p className="text-body-sm text-severityText-critical" role="alert">
            The recalibration could not run. No threshold was moved.
          </p>
        ) : null}
        <table className="w-full text-body-sm">
          <caption className="sr-only">
            Bands, the value in force, its source, and who last moved it
          </caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className="py-1">
                Band
              </th>
              <th scope="col" className="py-1">
                Value in force
              </th>
              <th scope="col" className="py-1">
                Source
              </th>
              <th scope="col" className="py-1">
                Last changed
              </th>
              <th scope="col" className="py-1">
                Set by hand
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.band} className="border-b border-line/50">
                <th scope="row" className="py-2 text-left font-normal">
                  {row.label}
                </th>
                <td className="py-2 font-mono">{formatThreshold(row.value)}</td>
                <td className="py-2">
                  <Badge tone="neutral">{row.source}</Badge>
                </td>
                <td className="py-2 text-muted">
                  {`${row.changedBy}${row.updatedAt === '' ? '' : ` · ${row.updatedAt}`}`}
                </td>
                <td className="py-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setEditing(row);
                    }}
                  >
                    {`Preview a new ${row.band} value`}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-body-sm text-muted">
          {`Everything below the ${formatThreshold(rows[rows.length - 1]?.value ?? 0)} ${BAND_WITHOUT_BOUND} bound is ${BAND_WITHOUT_BOUND}: it has no lower bound of its own, so there is nothing there to set.`}
        </p>
        <p className="text-body-sm text-muted">
          Sources:{' '}
          {rows.filter((row) => row.moved).length > 0
            ? 'a row exists for the bands that were moved'
            : 'no band has been moved on this deployment, so every value is FR-13\u2019s documented default'}
          . A recalibrated value and one set by hand are both stored the same way; the source is
          what tells them apart, and it is written by whoever moved it.
        </p>
      </div>

      {editing === null || active === null ? null : (
        <ThresholdEditor
          family={active}
          row={editing}
          onClose={() => {
            setEditing(null);
            set.reset();
          }}
          onSave={(value) => {
            set.mutate(
              { family: active, band: editing.band, value },
              {
                onSuccess: (result) => {
                  toast(
                    'success',
                    result.changed
                      ? `${result.family} ${result.band} is now ${formatThreshold(result.applied)} (was ${formatThreshold(result.previous)}).`
                      : `${result.family} ${result.band} already had that value; nothing was written.`,
                  );
                  setEditing(null);
                },
              },
            );
          }}
          refusal={thresholdRefusalMessage(set.error)}
          saving={set.isPending}
        />
      )}
    </Card>
  );
}

interface EditorProps {
  family: string;
  row: BandRow;
  onClose: () => void;
  onSave: (value: number) => void;
  refusal: string | null;
  saving: boolean;
}

/**
 * The editor, with the preview wired to the server.
 *
 * The counter is only asked for once the value could be saved, so a half-typed
 * "0." does not spend a counting read on the alert store. The reading is rendered
 * from `readPreview` — one place composes those sentences — so the caveat about a
 * capped walk cannot be forgotten by a later edit to this markup.
 */
function ThresholdEditor({ family, row, onClose, onSave, refusal, saving }: EditorProps) {
  const [text, setText] = useState(formatThreshold(row.value));
  const parsed = text.trim() === '' ? null : Number(text);
  const value = parsed !== null && Number.isFinite(parsed) ? parsed : null;
  const readiness = setReadiness(value, row.value);
  const preview = useThresholdPreview(family, row.band, value, readiness.ready);
  const reading = preview.data === undefined ? null : readPreview(preview.data);

  return (
    <Modal
      open
      title={`Set the ${family} ${row.band} threshold`}
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={saving}
            disabled={!readiness.ready || reading === null}
            onClick={() => {
              if (value !== null) onSave(value);
            }}
          >
            Save the value
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-body-sm text-muted">
          In force: <span className="font-mono">{formatThreshold(row.value)}</span> (
          {row.sourceLabel}
          {row.moved ? '' : ', never moved on this deployment'}).
        </p>
        <label className="flex flex-col gap-1 text-body-sm">
          {`Proposed ${row.band} lower bound`}
          <input
            value={text}
            inputMode="decimal"
            onChange={(event) => {
              setText(event.target.value);
            }}
            className="w-full max-w-xs rounded-control border border-line bg-base px-2 py-1 font-mono text-body"
          />
        </label>
        {readiness.reason === null ? null : (
          <p className="text-body-sm text-muted">{readiness.reason}</p>
        )}
        {refusal === null ? null : (
          <p className="text-body-sm text-severityText-critical" role="alert">
            {refusal}
          </p>
        )}
        {preview.isError ? (
          <p className="text-body-sm text-severityText-critical" role="alert">
            The impact preview could not be read, so nothing here can be saved: setting a threshold
            without knowing what it would have done is the one thing this dialog exists to prevent.
          </p>
        ) : null}
        {reading === null ? null : (
          <div className="flex flex-col gap-2 rounded-card border border-line bg-surface p-3">
            <p className="text-body">{reading.headline}</p>
            <p className="text-body-sm text-muted">{reading.change}</p>
            <p className="text-body-sm text-muted">{reading.basis}</p>
            {reading.caveat === null ? null : (
              <p className="text-body-sm text-severityText-critical" role="status">
                {reading.caveat}
              </p>
            )}
          </div>
        )}
        {preview.data?.complete === false ? (
          <p className="text-body-sm text-muted">
            A floored count does not block the save — a busy deployment would then never be able to
            move a threshold — but it does mean the number above understates the change.
          </p>
        ) : null}
      </div>
    </Modal>
  );
}
