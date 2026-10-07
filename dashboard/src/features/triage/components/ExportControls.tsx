/**
 * The alert batch's export (T-415, FR-23).
 *
 * Two buttons and one sentence, and each choice is deliberate:
 *
 * * **The window is the queue's own rule, applied at the click.** The body carries
 *   the query the queue reads with — the last 24 hours, newest first, one page of a
 *   hundred (`../api.ts`) — so the file's rows are the view's rows, which is T-415's
 *   acceptance criterion. The window is taken here rather than copied from a render:
 *   the queue re-reads on its own 15 s interval, so the two can differ by at most one
 *   refresh, and never by the rule.
 * * **The outcome is announced where the action was**, not in a toast. A toast
 *   interrupts from a corner of the screen; the operator's attention is on the
 *   queue, and what they need to know is a sentence about it — how many rows left,
 *   and that the trail records it (R-58's spirit: an egress is a thing that is
 *   written down). The region is `aria-live`, so the sentence is also heard.
 * * **The refusal is the server's.** A 403 is not predicted from a token the
 *   dashboard cannot verify; it is explained after the fact, with the fact that
 *   matters — nothing was downloaded and nothing was written to the trail.
 */
import { useState } from 'react';

import type { AlertExportFormat } from '../../../api/alerts';
import { exportRefusalMessage } from '../../../api/exports';
import { Button } from '../../../components/ui';
import { saveFile } from '../../../lib/download';
import { QUEUE_LIMIT, QUEUE_WINDOW_MS } from '../api';
import { useAlertExport } from '../hooks';

export function ExportControls() {
  const exportation = useAlertExport();
  const [outcome, setOutcome] = useState<string | null>(null);

  const refusal = exportRefusalMessage(exportation.error);

  const run = (format: AlertExportFormat): void => {
    // The queue's own window rule, applied now: the export reads the same newest-N
    // of the same last-24-h that the panel beside it is showing.
    const end = new Date();
    const start = new Date(end.getTime() - QUEUE_WINDOW_MS);
    setOutcome(null);
    exportation.mutate(
      { format, params: { start, end, limit: QUEUE_LIMIT, order: 'desc' } },
      {
        onSuccess: (result) => {
          saveFile({
            content: result.content,
            filename: result.filename ?? `aegis-alerts.${format}`,
          });
          const rows = result.rows === null ? 'the matching' : String(result.rows);
          const noun = result.rows === 1 ? 'row' : 'rows';
          const held = result.truncated
            ? ' The window holds more rows than the file does, so the trail records it as truncated.'
            : '';
          setOutcome(
            `Exported ${rows} ${noun} as ${format.toUpperCase()}.${held} The export is recorded in the audit trail.`,
          );
        },
      },
    );
  };

  const pending = (format: AlertExportFormat): boolean =>
    exportation.isPending && exportation.variables?.format === format;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={exportation.isPending}
          onClick={() => {
            run('csv');
          }}
        >
          {pending('csv') ? 'Exporting…' : 'Export CSV'}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={exportation.isPending}
          onClick={() => {
            run('pdf');
          }}
        >
          {pending('pdf') ? 'Exporting…' : 'Export PDF'}
        </Button>
      </div>
      <p aria-live="polite" className="text-caption text-muted">
        {refusal ?? outcome ?? ''}
      </p>
    </div>
  );
}
