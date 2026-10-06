/**
 * The hunt export's path and body, in one place (T-408).
 *
 * One read in this build answers with text rather than JSON: the CSV export. It is a
 * POST because the server records it as an audited egress, and its body is the query
 * definition — the same filter set `GET /api/v1/alerts` takes as query parameters, so
 * an export and the view it mirrors cannot disagree about what "matching" means.
 *
 * The builder deliberately cannot express a cursor: the API refuses one (pydantic
 * types it `None`), because an export mirrors the first page of the query the analyst
 * ran and a cursor would let a caller export a page nobody saw.
 */
import { postText } from './client';
import type { AlertListParams } from './alerts';

/** The export's endpoint. */
export const HUNT_EXPORT_PATH = '/api/v1/hunt/export';

/** The JSON body the export route takes: the alert query, as a document. */
export interface HuntExportBody {
  start: string;
  end: string;
  severity?: string;
  status?: string;
  family?: string;
  entity_id?: number;
  min_score?: number;
  order?: 'asc' | 'desc';
  limit?: number;
}

/** An instant as the API takes it: ISO-8601, always with a timezone. */
function instant(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : value;
}

/**
 * The query, as the export's body.
 *
 * Field names are the *wire* names (`entity_id`, `min_score`) rather than the
 * console's (`entity`, `min_score`): this is the one place that translation happens,
 * and doing it in a builder is what keeps the body and the list read identical.
 */
export function huntExportBody(params: AlertListParams): HuntExportBody {
  const body: HuntExportBody = {
    start: instant(params.start),
    end: instant(params.end),
  };
  if (params.severity !== undefined) body.severity = params.severity;
  if (params.status !== undefined) body.status = params.status;
  if (params.family !== undefined) body.family = params.family;
  if (params.entityId !== undefined) body.entity_id = params.entityId;
  if (params.minScore !== undefined) body.min_score = params.minScore;
  if (params.order !== undefined) body.order = params.order;
  if (params.limit !== undefined) body.limit = params.limit;
  return body;
}

/** Export the rows matching a hunt, as CSV text. */
export async function exportHunt(
  params: AlertListParams,
  options: { signal?: AbortSignal | undefined } = {},
): Promise<string> {
  return postText(HUNT_EXPORT_PATH, huntExportBody(params), options);
}
