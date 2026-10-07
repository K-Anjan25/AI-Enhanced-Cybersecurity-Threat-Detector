/**
 * What a refused export says, in the analyst's terms (T-408, T-415).
 *
 * Two screens export — the hunt console and the triage queue — and a 403 must not
 * be explained two different ways, so the copy lives beside the API it describes
 * rather than in either feature (a feature may not import another feature).
 *
 * A 403 is the *server's* answer rather than something the dashboard predicts: the
 * screen does not know the role, and inventing one from a token it cannot verify
 * would be a guess rendered as a rule. The sentence says what the operator can do
 * about it, and the fact that matters most is the one it also states — nothing was
 * written to the audit trail, because nothing was taken.
 */
import { ApiError } from './client';

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
