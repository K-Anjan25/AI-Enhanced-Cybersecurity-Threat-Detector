/**
 * The API keys panel's derived model (T-410, FR-44, D-042).
 *
 * T-410's second acceptance criterion — *the API key secret renders exactly once* —
 * has a shape that is easy to get wrong in a way no screenshot catches, so the rule
 * is encoded here rather than left to a component:
 *
 *   * **A secret has exactly one representation: `IssuedKey`.** It exists only as
 *     the value of the create mutation. `keyRows` produces rows from the *listing*,
 *     whose type (`ApiKey`) has no secret field, so there is no code path that could
 *     put a secret in the table even by accident.
 *   * **It is never stored, and it expires by itself.** The capture carries an
 *     `expiresWith` marker — the value of the panel's open-counter when the response
 *     arrived — and `secretIsLive` is the only predicate that decides whether it may
 *     be rendered. Closing the dialog passes `null` and kills it; reopening bumps the
 *     counter, so a dialog opened again cannot show a key from a previous rendering.
 *     There is no `setSecret(null)` to forget, and one mechanism rather than two.
 *   * **The prefix is what remains.** `aegis_sk_<id>_` is public (the id is inside
 *     the key), so the listing shows it and the panel explains that it is the
 *     visible half. A reader can match a row to a key they hold without the secret
 *     ever returning.
 *
 * The panel also states the one thing a copy-to-clipboard field invites people to
 * get wrong: there is no route that returns this value again, so a lost key is
 * re-issued rather than re-read.
 *
 * The capture and the predicate that reads it are shared with the connectors panel
 * (`secrets.ts`), because FR-44's API key and FR-21's signing secret are the same
 * rule about two credentials. What lives here is only what is true of a key.
 */
import { formatStamp } from '../../lib/format';
import type { ApiKey, ApiKeyIssued, ScopeInfo } from '../../api/admin';
import type { IssuedSecret } from './secrets';

/** A secret, with the lifetime it was given: the modal that received it. */
export interface IssuedKey extends IssuedSecret {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
}

/** Capture a create response, stamping it with the rendering that may show it. */
export function issuedKey(issued: ApiKeyIssued, expiresWith: number): IssuedKey {
  return {
    id: issued.id,
    name: issued.name,
    prefix: issued.prefix,
    scopes: [...issued.scopes],
    createdAt: issued.created_at,
    secret: issued.secret,
    expiresWith,
  };
}

/** The sentence the panel shows under the secret, which is the whole of the rule. */
export const SECRET_ONCE_NOTE =
  'This is the only time this key is shown. Only its prefix is stored, so a key you lose is re-issued rather than re-read.';

export interface KeyRow {
  id: number;
  name: string;
  /** The public half, `aegis_sk_<id>_`: what an operator matches a key to. */
  prefix: string;
  owner: string;
  scopes: string[];
  scopesText: string;
  createdAt: string;
  lastUsedAt: string;
  /** The revocation instant, or an empty string while the key works. */
  revokedAt: string;
  revoked: boolean;
}

/** The listing as rows. There is no secret in `ApiKey`, so none can appear here. */
export function keyRows(keys: readonly ApiKey[] | undefined): KeyRow[] {
  return (keys ?? []).map((key) => ({
    id: key.id,
    name: key.name,
    prefix: key.prefix,
    owner: key.owner,
    scopes: [...key.scopes],
    scopesText: key.scopes.join(', '),
    createdAt: formatStamp(key.created_at),
    lastUsedAt: key.last_used_at === null ? 'never used' : formatStamp(key.last_used_at),
    revokedAt: key.revoked_at === null ? '' : formatStamp(key.revoked_at),
    revoked: key.revoked_at !== null,
  }));
}

/** What the panel says above the table. */
export interface KeySummary {
  total: number;
  live: number;
  revoked: number;
  note: string;
}

export function keySummary(keys: readonly ApiKey[] | undefined): KeySummary {
  const all = keys ?? [];
  const revoked = all.filter((key) => key.revoked_at !== null).length;
  const live = all.length - revoked;
  return {
    total: all.length,
    live,
    revoked,
    note:
      all.length === 0
        ? 'No keys have been issued. A key is a machine credential for ingestion (FR-44), and revoking one takes effect on the next request.'
        : `${String(live)} live, ${String(revoked)} revoked. Revoked keys keep their row: it is the record of a credential having existed.`,
  };
}

/** One scope choice, with what it grants. */
export interface ScopeChoice {
  name: string;
  capabilities: string[];
  describes: string;
}

const SCOPE_LABELS: Readonly<Record<string, string>> = {
  'ingest:write': 'write ingested telemetry',
  'alerts:read': 'read the alert list',
  ingest_write: 'write ingested telemetry',
  alerts_read: 'read the alert list',
};

export function scopeChoices(scopes: readonly ScopeInfo[] | undefined): ScopeChoice[] {
  return (scopes ?? []).map((scope) => ({
    name: scope.name,
    capabilities: [...scope.capabilities],
    describes: SCOPE_LABELS[scope.name] ?? scope.capabilities.join(', '),
  }));
}

/** Whether a key can be created: a name and at least one scope (the API's rule). */
export function creationReadiness(
  name: string,
  scopes: readonly string[],
): {
  ready: boolean;
  reason: string | null;
} {
  if (name.trim() === '') return { ready: false, reason: 'A key needs a name to recognise it by.' };
  if (name.trim().length > 120) {
    return { ready: false, reason: 'A key name may be at most 120 characters.' };
  }
  if (scopes.length === 0) {
    return {
      ready: false,
      reason: 'A key needs at least one scope: an empty scope set is not a key.',
    };
  }
  return { ready: true, reason: null };
}
