/**
 * The admin API's wire shapes and paths (T-410): users, roles, keys, thresholds,
 * retention and the audit trail.
 *
 * One module for six surfaces, because they are one screen's worth of work and
 * because two of the six carry a rule that must not be restated anywhere else:
 *
 *   * **`ApiKeyIssued` is a different type from `ApiKey`, and only the create call
 *     returns it.** `ApiKey` has no secret field, so the listing cannot render one
 *     even if someone wanted it to: the type is the guarantee design.md §4.8's
 *     "shown exactly once" rests on, and a screen that stored the issued key in
 *     React Query's cache would keep it alive past its one rendering. The create
 *     mutation therefore returns it *and never caches it* (see `features/admin`).
 *   * **The last-admin rule is the server's.** `UserList.active_admins` is the count
 *     the server decides the refusal by, so the screen marks the last admin with the
 *     server's number rather than counting rows itself.
 *
 * The threshold preview is a GET with its value in the query string: it writes
 * nothing, it is readable by every role, and it is the number the operator sees
 * *before* saving — which is exactly what design.md §4.8 asks for.
 */
import { deleteJson, getJson, postJson, putJson, query } from './client';

// --- users and roles ---------------------------------------------------------

/** One user, as `GET /api/v1/users` returns them. No credential field exists. */
export interface AdminUser {
  id: number;
  email: string;
  role: string;
  created_at: string;
  disabled_at: string | null;
}

export interface UserList {
  items: AdminUser[];
  count: number;
  /** Accounts that can currently administer. The number the refusal is decided by. */
  active_admins: number;
}

/** One role with what it may do, read from the server's own capability matrix. */
export interface RoleInfo {
  role: string;
  capabilities: string[];
}

export interface RoleList {
  items: RoleInfo[];
}

export interface RoleChange {
  user_id: number;
  previous: string;
  applied: string;
  /** False when the user already held the role: nothing was written or audited. */
  changed: boolean;
  at: string;
  actor: string;
}

export const USERS_PATH = '/api/v1/users';

/** `POST /api/v1/users/{user_id}/role`. */
export function userRolePath(userId: number): string {
  return `${USERS_PATH}/${String(userId)}/role`;
}

export async function fetchUsers(signal?: AbortSignal): Promise<UserList> {
  return getJson<UserList>(USERS_PATH, { signal });
}

export async function fetchRoles(signal?: AbortSignal): Promise<RoleList> {
  return getJson<RoleList>(`${USERS_PATH}/roles`, { signal });
}

/**
 * Set one user's role.
 *
 * A 409 means the server refused: the change would leave no active admin. The
 * message is the server's, and the screen renders it rather than a sentence of its
 * own — the rule and the explanation live in one place (R-53).
 */
export async function changeUserRole(userId: number, role: string): Promise<RoleChange> {
  return postJson<RoleChange>(userRolePath(userId), { role });
}

// --- API keys ----------------------------------------------------------------

/** One key as the listing returns it: a prefix, never the secret. */
export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  owner: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/**
 * A newly issued key.
 *
 * The only type in the dashboard that carries a secret, and it exists only as the
 * answer to one POST. There is no route that returns it again: the server stores a
 * digest, so a lost key is re-issued rather than re-read.
 */
export interface ApiKeyIssued extends ApiKey {
  secret: string;
}

export interface ApiKeyList {
  items: ApiKey[];
}

export interface ScopeInfo {
  name: string;
  capabilities: string[];
}

export interface ScopeList {
  items: ScopeInfo[];
}

export const KEYS_PATH = '/api/v1/keys';

/** `DELETE /api/v1/keys/{key_id}` — revoke, which is not a delete (T-313). */
export function keyPath(keyId: number): string {
  return `${KEYS_PATH}/${String(keyId)}`;
}

export async function fetchKeys(signal?: AbortSignal): Promise<ApiKeyList> {
  return getJson<ApiKeyList>(KEYS_PATH, { signal });
}

export async function fetchScopes(signal?: AbortSignal): Promise<ScopeList> {
  return getJson<ScopeList>(`${KEYS_PATH}/scopes`, { signal });
}

/** Issue a key. The response is the one and only place its secret exists. */
export async function createKey(name: string, scopes: readonly string[]): Promise<ApiKeyIssued> {
  return postJson<ApiKeyIssued>(KEYS_PATH, { name, scopes: [...scopes] });
}

/** Revoke a key. Idempotent server-side; the first revocation keeps its instant. */
export async function revokeKey(keyId: number): Promise<void> {
  await deleteJson(keyPath(keyId));
}

// --- thresholds --------------------------------------------------------------

/** One stored threshold row, with its provenance and its last writer. */
export interface Threshold {
  tenant_id: string;
  family: string;
  band: string;
  value: number;
  /** As stored: `recalculation` for a fitted value, `manual` for one a person set. */
  source: string;
  /** design.md §4.8's vocabulary: `calibrated` or `manual`. */
  source_label: string;
  updated_at: string;
  changed_by: string | null;
}

export interface ThresholdList {
  tenant_id: string;
  /** FR-13's documented bounds, in force wherever no row exists. */
  defaults: Record<string, number>;
  items: Threshold[];
}

/** What a hand-set threshold did, including when it changed nothing. */
export interface ThresholdSet {
  tenant_id: string;
  family: string;
  band: string;
  previous: number;
  previous_label: string;
  applied: number;
  source: string;
  changed: boolean;
  at: string;
}

/** What a proposed value would have done over the preview window. */
export interface ThresholdImpact {
  tenant_id: string;
  family: string;
  band: string;
  proposed: number;
  current: number;
  current_source: string;
  window_start: string;
  window_end: string;
  alerts_read: number;
  would_fire: number;
  would_stop_firing: number;
  would_start_firing: number;
  /** False when the page cap stopped the walk: the counts are a floor, not a total. */
  complete: boolean;
}

/** A recalibration run: what moved, what was left alone and why. */
export interface RecalibrationOutcome {
  family: string;
  band: string;
  previous: number;
  previous_was_default: boolean;
  requested: number | null;
  applied: number | null;
  changed: boolean;
  clamped: boolean;
  sample_size: number;
  reason: string;
}

/**
 * A run's report: the window it read, and every threshold it considered.
 *
 * `window_days` used to stand where `since`/`until`/`quantile` belong — a field
 * `RecalibrationOut` has never carried (`backend/app/schemas/thresholds.py`), so the
 * panel's toast read "Recalibration ran over undefined days". The window is the
 * job's own 14 days (`DEFAULT_WINDOW`) but the response does not assume a reader
 * knows that: it says which two instants it read, and this type repeats them.
 */
export interface RecalibrationResult {
  tenant_id: string;
  band: string;
  at: string;
  /** Start of the window the fit read, inclusive. */
  since: string;
  /** End of it, exclusive — the run's own instant. */
  until: string;
  /** The quantile the fit used: the false-positive budget, inverted. */
  quantile: number;
  /** The floor of labelled alerts a family's fit had to clear. */
  minimum_sample: number;
  considered: number;
  changed: number;
  outcomes: RecalibrationOutcome[];
}

export const THRESHOLDS_PATH = '/api/v1/thresholds';

/** `PUT /api/v1/thresholds/{family}/{band}` — one manual edit. */
export function thresholdPath(family: string, band: string): string {
  return `${THRESHOLDS_PATH}/${encodeURIComponent(family)}/${encodeURIComponent(band)}`;
}

export async function fetchThresholds(signal?: AbortSignal): Promise<ThresholdList> {
  return getJson<ThresholdList>(THRESHOLDS_PATH, { signal });
}

/** Count a proposed value against the recorded alerts. Writes nothing. */
export async function previewThreshold(
  family: string,
  band: string,
  value: number,
  options: { signal?: AbortSignal | undefined } = {},
): Promise<ThresholdImpact> {
  return getJson<ThresholdImpact>(
    `${THRESHOLDS_PATH}/preview${query({ family, band, value })}`,
    options,
  );
}

/** Set one threshold by hand. A 409 means the value would invert the band order. */
export async function setThreshold(
  family: string,
  band: string,
  value: number,
): Promise<ThresholdSet> {
  return putJson<ThresholdSet>(thresholdPath(family, band), { value });
}

/** Run the weekly recalibration now (FR-18, T-322). */
export async function recalibrateThresholds(band = 'high'): Promise<RecalibrationResult> {
  return postJson<RecalibrationResult>(`${THRESHOLDS_PATH}/recalibrate`, { band });
}

// --- retention and erasure ---------------------------------------------------

export interface RetentionPolicy {
  raw_records_days: number;
  alerts_days: number;
  stats_days: number;
}

/** One monthly partition, with the DDL a drop would execute. */
export interface WindowPartition {
  table: string;
  name: string;
  year: number;
  month: number;
  covers_start: string;
  covers_end: string;
  statement: string;
}

/**
 * A table retention will not touch, and why.
 *
 * One entry per table, keyed by the table itself: `UnevictableOut` is
 * `{table, reason}`, and this interface declared a `name` the server has never
 * sent — which the drop list's rows also have, so the extra field read as though
 * the two lists shared a shape. It did not, and every consumer of `name` was
 * handed `undefined`.
 */
export interface Unevictable {
  table: string;
  reason: string;
}

/** What a retention run would do, and what it will never reach. */
export interface RetentionPlan {
  planned_at: string;
  policy: RetentionPolicy;
  drop: WindowPartition[];
  kept: WindowPartition[];
  /** Months inside the window with no partition: rows were rejected at insert. */
  missing: string[];
  unevictable: Unevictable[];
  /** Stores the plan cannot reach from the database, and what each one is. */
  external: Record<string, string>;
  statements: string[];
}

export interface RetentionRun {
  started_at: string;
  planned: string[];
  dropped: string[];
  already_absent: string[];
  changed_anything: boolean;
}

export interface ErasureTarget {
  name: string;
  affected: number;
}

/** A store the erasure left alone, and why. */
export interface PreservedLedger {
  name: string;
  reason: string;
}

export interface ErasureReport {
  kind: string;
  tombstone: string;
  at: string;
  targets: ErasureTarget[];
  /**
   * The append-only stores the erasure did not rewrite, with the server's reason.
   *
   * `name`, not `store`: the wire field is `PreservedLedgerOut.name`
   * (`backend/app/schemas/privacy.py`), and this type said `store` until T-423 —
   * so the panel rendered `undefined` for every preserved entry it was handed, in
   * the one sentence that tells a data subject what was *not* erased.
   */
  preserved: PreservedLedger[];
  already_erased: boolean;
  ledger_sequence: number | null;
  affected: number;
  reason: string;
}

export const RETENTION_PATH = '/api/v1/retention';

export async function fetchRetention(signal?: AbortSignal): Promise<RetentionPlan> {
  return getJson<RetentionPlan>(RETENTION_PATH, { signal });
}

/**
 * Run retention now.
 *
 * Refused with a 500 when no partition runner is wired — this build has no
 * database session, and the server says so rather than reporting a clean run it
 * did not perform. The screen renders that refusal as itself.
 */
export async function runRetention(): Promise<RetentionRun> {
  return postJson<RetentionRun>(`${RETENTION_PATH}/run`, {});
}

/** Erase one data subject across every store (NFR-05, R-37). */
export async function eraseSubject(
  kind: 'user' | 'entity',
  value: string,
  reason: string,
): Promise<ErasureReport> {
  return postJson<ErasureReport>('/api/v1/privacy/erasure', { kind, value, reason });
}

// --- audit -------------------------------------------------------------------

/** One recorded action. `detail` is the thin context the writing route supplied. */
export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: Record<string, unknown>;
  ip: string | null;
  at: string;
}

export interface AuditPage {
  items: AuditEntry[];
  next_before: number | null;
}

export interface AuditQuery {
  start: Date;
  end: Date;
  action?: string | undefined;
  actor?: string | undefined;
  targetType?: string | undefined;
  targetId?: string | undefined;
  before?: number | undefined;
  limit?: number | undefined;
  signal?: AbortSignal | undefined;
}

export const AUDIT_PATH = '/api/v1/audit';

/** `GET /api/v1/audit` — one bounded page, newest first (R-34 applies here too). */
export async function fetchAudit(params: AuditQuery): Promise<AuditPage> {
  const { start, end, signal, targetType, targetId, before, limit, ...rest } = params;
  return getJson<AuditPage>(
    `${AUDIT_PATH}${query({
      ...rest,
      start: start.toISOString(),
      end: end.toISOString(),
      target_type: targetType,
      target_id: targetId,
      before,
      limit,
    })}`,
    { signal },
  );
}
