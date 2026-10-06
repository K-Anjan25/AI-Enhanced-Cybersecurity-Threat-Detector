/**
 * The hunt console's data wiring (T-408).
 *
 * **A hunt is a question, not a stream.** Nothing here polls: the search runs when
 * the analyst runs it, and the same parameters keep returning the same page until
 * they ask again. That is the opposite of the tail (T-407, two seconds) and the
 * overview (T-403, fifteen), and it is deliberate — a table that re-sorted itself
 * under a reader comparing two rows would be worse than a stale one.
 *
 * **The export is a mutation.** It is not data the screen keeps: it is an action
 * with a pending state, a possible refusal (the role check is the server's) and a
 * result the analyst has to be told about, which is exactly what a mutation models.
 * The refetch-after-export that React Query does by default is switched off: the
 * rows did not change because somebody took a copy of them.
 */
import {
  useMutation,
  useQuery,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { fetchAlertPage, type AlertListParams, type AlertPage } from '../../api/alerts';
import { ApiError } from '../../api/client';
import { exportHunt } from '../../api/hunt';

/** The alert page this console reads: one bounded read, no cursor walk. */
export function useHuntSearch(
  params: AlertListParams | null,
  enabled = true,
): UseQueryResult<AlertPage, Error> {
  return useQuery({
    queryKey: ['hunt', 'search', params ?? null],
    queryFn: ({ signal }) => {
      if (params === null) throw new Error('a hunt with no query cannot be read');
      return fetchAlertPage(params, { signal });
    },
    enabled: enabled && params !== null,
  });
}

/** The result of one export, as the panel reports it. */
export interface HuntExportResult {
  csv: string;
  /** How many data rows the file carries, counted from the document itself. */
  rows: number;
}

/** Count the data rows of a CSV document, ignoring the header and blank lines. */
export function csvRowCount(csv: string): number {
  const lines = csv.split(/\r\n|\n/).filter((line) => line.trim() !== '');
  return Math.max(0, lines.length - 1);
}

/** Export a hunt's rows. The caller decides what to do with the document. */
export function useHuntExport(): UseMutationResult<HuntExportResult, Error, AlertListParams> {
  return useMutation({
    mutationFn: async (params: AlertListParams) => {
      const csv = await exportHunt(params);
      return { csv, rows: csvRowCount(csv) };
    },
  });
}

/**
 * What a refused export should say, in the analyst's terms.
 *
 * A 403 is the only refusal this route produces for a signed-in caller, and it is
 * the *server's* answer rather than something the dashboard predicts: the screen
 * does not know the role, and inventing one from a token it cannot verify would be
 * a guess rendered as a rule.
 */
export function exportRefusalMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 403) {
    return 'Exporting needs the responder role. Your account does not have it, so nothing was written to the audit trail.';
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'The session is not authenticated, so the export was refused.';
  }
  return 'The export could not be read. Nothing was downloaded.';
}
