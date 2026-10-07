/**
 * The raw lines behind one cluster: what "×10,000" was hiding.
 *
 * Oldest first, because expanding a cluster is usually reading a stack trace and a
 * trace read backwards is a different story. When the read hit its row limit the
 * panel says so *and* which end it kept — the newest lines, since that is the end a
 * tail's reader is looking at — rather than silently showing a prefix.
 *
 * The lines are a snapshot: the panel is filled when a row is opened and not on an
 * interval (a reader who has a cluster open must be able to finish reading it, which
 * is the same argument the pause control makes for the whole screen). The header
 * carries the API's first caveat, which is the sentence naming where these lines came
 * from — a tail's own bounds or the store's — so an expansion taken from a fifteen-
 * minute buffer cannot read as though it were a stored read (T-419).
 */
import { Badge, Button, Card, ErrorState, Skeleton } from '../../../components/ui';
import { formatCount, formatStamp } from '../../../lib/format';
import { levelTone } from '../cluster';
import type { LogLines } from '../api';

export interface RawLinesProps {
  /** The cluster being shown, or null when nothing is open. Deliberately not `key`:
   * React reserves that name, and a panel that silently received the cluster id as
   * its identity would remount instead of updating. */
  clusterKey: string | null;
  template: string;
  lines: LogLines | undefined;
  failed: boolean;
  onClose: () => void;
}

export function RawLines({ clusterKey, template, lines, failed, onClose }: RawLinesProps) {
  if (clusterKey === null) return null;

  return (
    <Card
      title={`Raw lines · ${template}`}
      actions={
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      }
    >
      {failed ? (
        <ErrorState
          message="The raw lines could not be read"
          detail="The cluster is still listed; closing and reopening it retries the read."
          action={<Button onClick={onClose}>Close</Button>}
        />
      ) : lines === undefined ? (
        <Skeleton lines={4} />
      ) : (
        <div id="log-raw-lines">
          <p className="mb-2 text-caption text-muted">
            {lines.lines_truncated
              ? `Showing the newest ${formatCount(lines.lines.length)} of ${formatCount(lines.lines_seen)} matching lines.`
              : `All ${formatCount(lines.lines_seen)} matching lines in the window.`}{' '}
            {lines.caveats[0] ?? ''}
          </p>
          <ol className="space-y-1 font-mono text-body-sm">
            {lines.lines.map((line) => (
              <li key={`${line.timestamp}-${line.host}-${line.message}`} className="flex gap-2">
                <span className="shrink-0 tabular-nums text-muted">
                  {formatStamp(line.timestamp)}
                </span>
                <span className="shrink-0 text-muted">{line.host}</span>
                <Badge tone={levelTone(line.level)}>{line.level}</Badge>
                <span className="break-all">{line.message}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}
