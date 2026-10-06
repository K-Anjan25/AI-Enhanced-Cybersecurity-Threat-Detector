/**
 * The admin screens' data wiring (T-410).
 *
 * Six reads and five writes, with two properties that are decisions rather than
 * plumbing:
 *
 *   * **A cookie-cutter cadence, and no polling.** Nothing here polls. An admin
 *     screen changes when an operator acts on it, and every mutation invalidates
 *     the keys it touched, so what is on screen after a change is re-read rather
 *     than aged. The one exception is the threshold preview, which is a *query* the
 *     operator drives and therefore keeps its previous value while the next one
 *     arrives — otherwise the panel blinks between numbers as the value is typed.
 *   * **The issued key's secret is never cached.** `useIssueKey` returns the
 *     response and invalidates the listing; the mutation itself is not kept, and no
 *     query key holds a secret. React Query's devtools, its cache and a
 *     `staleTime`-driven refetch therefore have nothing to leak: the only place the
 *     secret exists is the value the caller got and the modal lifetime it was
 *     stamped with (see `keys.ts`).
 *
 * Refusals are mapped to sentences by status, because this client never parses an
 * error body (R-58: a body echoes the request back). The 409 on a role change is
 * the one that matters: it is the last-admin rule, and the sentence names it.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import {
  changeUserRole,
  createKey,
  eraseSubject,
  fetchAudit,
  fetchKeys,
  fetchRetention,
  fetchRoles,
  fetchThresholds,
  fetchUsers,
  previewThreshold,
  recalibrateThresholds,
  revokeKey,
  runRetention,
  setThreshold,
  type ApiKeyIssued,
  type AuditPage,
  type AuditQuery,
  type ErasureReport,
  type RecalibrationResult,
  type RetentionPlan,
  type RetentionRun,
  type RoleChange,
  type RoleList,
  type ScopeList,
  type ThresholdImpact,
  type ThresholdList,
  type ThresholdSet,
  type UserList,
} from '../../api/admin';
import { fetchScopes } from '../../api/admin';

/** The directory and the count the last-admin rule is decided by. */
export function useUsers(): UseQueryResult<UserList, Error> {
  return useQuery({ queryKey: ['admin', 'users'], queryFn: ({ signal }) => fetchUsers(signal) });
}

/** R-53's roles with their capabilities, from the server's own matrix. */
export function useRoles(): UseQueryResult<RoleList, Error> {
  return useQuery({ queryKey: ['admin', 'roles'], queryFn: ({ signal }) => fetchRoles(signal) });
}

export function useKeys(): UseQueryResult<
  { items: Awaited<ReturnType<typeof fetchKeys>>['items'] },
  Error
> {
  return useQuery({ queryKey: ['admin', 'keys'], queryFn: ({ signal }) => fetchKeys(signal) });
}

export function useScopes(): UseQueryResult<ScopeList, Error> {
  return useQuery({ queryKey: ['admin', 'scopes'], queryFn: ({ signal }) => fetchScopes(signal) });
}

export function useThresholds(): UseQueryResult<ThresholdList, Error> {
  return useQuery({
    queryKey: ['admin', 'thresholds'],
    queryFn: ({ signal }) => fetchThresholds(signal),
  });
}

/**
 * The impact preview for one proposed value.
 *
 * `enabled` is the caller's: the panel asks only when the operator has typed a
 * value that could be saved, so typing "0." does not fire a counting read against
 * the alert store.
 */
export function useThresholdPreview(
  family: string,
  band: string,
  value: number | null,
  enabled: boolean,
): UseQueryResult<ThresholdImpact, Error> {
  return useQuery({
    queryKey: ['admin', 'thresholds', 'preview', family, band, value],
    queryFn: ({ signal }) => previewThreshold(family, band, value ?? 0, { signal }),
    enabled: enabled && value !== null,
    // Keep the last preview on screen while the next one arrives: a panel that
    // blanked on every keystroke would make the number impossible to read.
    placeholderData: keepPreviousData,
  });
}

/** The audit trail, one bounded window at a time. */
export function useAudit(params: AuditQuery): UseQueryResult<AuditPage, Error> {
  return useQuery({
    queryKey: [
      'admin',
      'audit',
      params.start.toISOString(),
      params.end.toISOString(),
      params.action ?? null,
      params.actor ?? null,
      params.targetType ?? null,
      params.targetId ?? null,
      params.before ?? null,
    ],
    queryFn: ({ signal }) => fetchAudit({ ...params, signal }),
  });
}

/** What a retention run would do right now. */
export function useRetention(): UseQueryResult<RetentionPlan, Error> {
  return useQuery({
    queryKey: ['admin', 'retention'],
    queryFn: ({ signal }) => fetchRetention(signal),
  });
}

// --- mutations ---------------------------------------------------------------

/**
 * Change one user's role.
 *
 * A 409 is the last-admin refusal. The sentence names the rule rather than
 * repeating the server's body, because the body is not read (R-58) — and the rule
 * is the one thing a reader needs to know to fix it.
 */
export function useChangeRole(): UseMutationResult<
  RoleChange,
  Error,
  { userId: number; role: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }) => changeUserRole(userId, role),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'users'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

/**
 * Issue a key.
 *
 * The result is the secret and is **not** written to the query cache: the mutation's
 * own state holds it until the caller takes it, and the listing is invalidated so
 * the new row appears without a secret in it.
 */
export function useIssueKey(): UseMutationResult<
  ApiKeyIssued,
  Error,
  { name: string; scopes: string[] }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, scopes }) => createKey(name, scopes),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'keys'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

export function useRevokeKey(): UseMutationResult<void, Error, number> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (keyId: number) => revokeKey(keyId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'keys'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

export function useSetThreshold(): UseMutationResult<
  ThresholdSet,
  Error,
  { family: string; band: string; value: number }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ family, band, value }) => setThreshold(family, band, value),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'thresholds'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

export function useRecalibrate(): UseMutationResult<
  RecalibrationResult,
  Error,
  string | undefined
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (band: string | undefined) => recalibrateThresholds(band),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'thresholds'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

export function useRunRetention(): UseMutationResult<RetentionRun, Error, void> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => runRetention(),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'retention'] });
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

export function useEraseSubject(): UseMutationResult<
  ErasureReport,
  Error,
  { kind: 'user' | 'entity'; value: string; reason: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, value, reason }) => eraseSubject(kind, value, reason),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'audit'] });
    },
  });
}

// --- refusal sentences -------------------------------------------------------

/** What a failed role change means, by status. The body is never read (R-58). */
export function roleRefusalMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError) {
    switch (error.status) {
      case 403:
        return 'Changing roles needs the admin role. Your account does not have it.';
      case 409:
        return 'The server refused: this change would leave the deployment with no active admin (R-53). Give another account the admin role first.';
      case 400:
        return 'The server does not know that role. R-53 has four: viewer, analyst, responder and admin.';
      case 404:
        return 'That account is no longer in the directory. Reload to see who is.';
      default:
        break;
    }
  }
  return 'The role change could not be sent. Nothing was changed.';
}

/** What a failed key issue or revoke means, by status. */
export function keyRefusalMessage(error: Error | null, what: 'issue' | 'revoke'): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 403) {
    return `Issuing and revoking keys needs the admin role. Your account cannot ${what} keys.`;
  }
  if (error instanceof ApiError && error.status === 422) {
    return 'The server refused the request as malformed: a key needs a name and at least one scope.';
  }
  return what === 'issue'
    ? 'The key could not be issued. Nothing was created.'
    : 'The key could not be revoked. It is still live.';
}

/** What a failed threshold write means, by status. */
export function thresholdRefusalMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError) {
    switch (error.status) {
      case 403:
        return 'Moving a threshold needs the admin role. Your account cannot change it.';
      case 409:
        return 'The server refused: that value would leave the bands out of order. Every band must stay strictly below the one above it.';
      case 400:
        return 'The server refused: that band has no lower bound to move, or the value is not a proportion.';
      default:
        break;
    }
  }
  return 'The threshold could not be saved. The value in force is unchanged.';
}

/** What a failed retention run means. The 500 is this build's own honest answer. */
export function retentionRefusalMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 403) {
    return 'Running retention needs the admin role. Your account cannot run it.';
  }
  if (error instanceof ApiError && (error.status ?? 0) >= 500) {
    return 'The run failed on the server. This build has no database session wired to drop partitions, so the route refuses rather than reporting a run it did not perform (D-030).';
  }
  return 'The retention run could not be sent. Nothing was dropped.';
}
