/**
 * The log explorer's data source, named in its own slice.
 *
 * The wire shapes, the two paths and the level vocabulary live in
 * `src/api/logs.ts`, because the hunt console (T-408) will read raw records through
 * the same endpoints and a feature may not import another feature (R-15). This
 * module is the seam the feature imports from, so `hooks.ts` and `view.ts` never
 * reach across two layers for a type.
 */
export { fetchLogLines, fetchLogTail, LOG_LEVELS } from '../../api/logs';
export type { LogCluster, LogLevel, LogLines, LogTail } from '../../api/logs';
