/**
 * The admin client's paths, methods and bodies (T-410).
 *
 * The method is part of the contract here in a way it is not elsewhere: the threshold
 * write is a `PUT` because it replaces the value in force, the revoke is a `DELETE`
 * because that is what the API serves, and the preview is a `GET` *because it writes
 * nothing* — a read that changed data would be a preview an operator could not safely
 * ask for. Those three are asserted as methods, not just as URLs.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, stubFetch } from '../test/query';
import {
  AUDIT_PATH,
  KEYS_PATH,
  RETENTION_PATH,
  THRESHOLDS_PATH,
  USERS_PATH,
  changeUserRole,
  createKey,
  eraseSubject,
  fetchAudit,
  fetchRetention,
  fetchThresholds,
  fetchUsers,
  previewThreshold,
  revokeKey,
  runRetention,
  setThreshold,
  thresholdPath,
  userRolePath,
} from './admin';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('paths', () => {
  it('addresses a role change under the user it changes', () => {
    expect(userRolePath(7)).toBe(`${USERS_PATH}/7/role`);
  });

  it('keeps a family and a band inside one segment each', () => {
    expect(thresholdPath('flow', 'high')).toBe(`${THRESHOLDS_PATH}/flow/high`);
    expect(thresholdPath('a/b', 'c d')).toBe(`${THRESHOLDS_PATH}/a%2Fb/c%20d`);
  });
});

describe('users', () => {
  it('reads the directory from the collection path', async () => {
    const seen = stubFetch([
      { match: USERS_PATH, respond: () => jsonResponse({ items: [], count: 0, active_admins: 0 }) },
    ]);
    await fetchUsers();
    expect(new URL(seen[0]?.url ?? '').pathname).toBe(USERS_PATH);
    expect(seen[0]?.method).toBe('GET');
  });

  it('posts the role as JSON, and nothing else', async () => {
    const seen = stubFetch([
      {
        match: USERS_PATH,
        respond: () =>
          jsonResponse({
            user_id: 7,
            previous: 'viewer',
            applied: 'analyst',
            changed: true,
            at: '2026-10-06T00:00:00Z',
            actor: 'ops@example.test',
          }),
      },
    ]);
    const result = await changeUserRole(7, 'analyst');
    expect(result.changed).toBe(true);
    const request = seen[0];
    expect(request?.method).toBe('POST');
    expect(new URL(request?.url ?? '').pathname).toBe(`${USERS_PATH}/7/role`);
    await expect(request?.json()).resolves.toEqual({ role: 'analyst' });
  });
});

describe('keys', () => {
  it('issues a key with the scopes it was given, and reads the secret back', async () => {
    const seen = stubFetch([
      {
        match: KEYS_PATH,
        respond: () =>
          jsonResponse({
            id: 1,
            name: 'c1',
            prefix: 'aegis_sk_1_',
            owner: 'ops',
            scopes: ['ingest:write'],
            created_at: '2026-10-06T00:00:00Z',
            last_used_at: null,
            revoked_at: null,
            secret: 'aegis_sk_1_deadbeef', // pragma: allowlist secret -- a test fixture
          }),
      },
    ]);
    const issued = await createKey('c1', ['ingest:write']);
    expect(issued.secret).toBe('aegis_sk_1_deadbeef');
    await expect(seen[0]?.json()).resolves.toEqual({ name: 'c1', scopes: ['ingest:write'] });
  });

  it('revokes with DELETE and reads no body back', async () => {
    const seen = stubFetch([
      { match: KEYS_PATH, respond: () => new Response(null, { status: 204 }) },
    ]);
    await expect(revokeKey(3)).resolves.toBeUndefined();
    expect(seen[0]?.method).toBe('DELETE');
    expect(new URL(seen[0]?.url ?? '').pathname).toBe(`${KEYS_PATH}/3`);
  });
});

describe('thresholds', () => {
  it('reads the list with its defaults', async () => {
    const seen = stubFetch([
      {
        match: THRESHOLDS_PATH,
        respond: () => jsonResponse({ tenant_id: 't1', defaults: { high: 0.7 }, items: [] }),
      },
    ]);
    const list = await fetchThresholds();
    expect(list.defaults['high']).toBe(0.7);
    expect(seen[0]?.method).toBe('GET');
  });

  it('previews with a GET carrying the family, the band and the value', async () => {
    // The method is the point: a preview that wrote something would be an action
    // taken by a control labelled "preview".
    const seen = stubFetch([
      {
        match: `${THRESHOLDS_PATH}/preview`,
        respond: () =>
          jsonResponse({
            tenant_id: 't1',
            family: 'flow',
            band: 'high',
            proposed: 0.8,
            current: 0.7,
            current_source: 'manual',
            window_start: '2026-09-29T00:00:00Z',
            window_end: '2026-10-06T00:00:00Z',
            alerts_read: 412,
            would_fire: 98,
            would_stop_firing: 12,
            would_start_firing: 0,
            complete: true,
          }),
      },
    ]);
    const impact = await previewThreshold('flow', 'high', 0.8);
    expect(impact.would_fire).toBe(98);
    const request = seen[0];
    expect(request?.method).toBe('GET');
    const url = new URL(request?.url ?? '');
    expect(url.pathname).toBe(`${THRESHOLDS_PATH}/preview`);
    expect(url.searchParams.get('family')).toBe('flow');
    expect(url.searchParams.get('band')).toBe('high');
    expect(url.searchParams.get('value')).toBe('0.8');
  });

  it('proposes a value with PUT, which is what replaces the row in force', async () => {
    const seen = stubFetch([
      {
        match: THRESHOLDS_PATH,
        respond: () =>
          jsonResponse({
            tenant_id: 't1',
            family: 'flow',
            band: 'high',
            previous: 0.7,
            previous_label: 'manual',
            applied: 0.8,
            source: 'manual',
            changed: true,
            at: '2026-10-06T00:00:00Z',
          }),
      },
    ]);
    const result = await setThreshold('flow', 'high', 0.8);
    expect(result.applied).toBe(0.8);
    expect(seen[0]?.method).toBe('PUT');
    await expect(seen[0]?.json()).resolves.toEqual({ value: 0.8 });
  });
});

describe('retention and erasure', () => {
  it('posts an erasure with the kind, the identifier and the reason', async () => {
    const seen = stubFetch([
      {
        match: '/api/v1/privacy/erasure',
        respond: () =>
          jsonResponse({
            kind: 'user',
            tombstone: 'sha256:abc',
            at: '2026-10-06T00:00:00Z',
            targets: [],
            preserved: [],
            already_erased: false,
            ledger_sequence: 1,
            affected: 0,
            reason: '',
          }),
      },
    ]);
    await eraseSubject('user', 'someone@example.test', 'request 42');
    const request = seen[0];
    expect(request?.method).toBe('POST');
    expect(new URL(request?.url ?? '').pathname).toBe('/api/v1/privacy/erasure');
    await expect(request?.json()).resolves.toEqual({
      kind: 'user',
      value: 'someone@example.test',
      reason: 'request 42',
    });
  });

  it('reads the retention plan from its own path', async () => {
    const seen = stubFetch([
      {
        match: RETENTION_PATH,
        respond: () => jsonResponse({ planned_at: '2026-10-06T00:00:00Z' }),
      },
    ]);
    await fetchRetention();
    expect(new URL(seen[0]?.url ?? '').pathname).toBe(RETENTION_PATH);
    expect(seen[0]?.method).toBe('GET');
  });

  it('runs retention with POST, because a run writes', async () => {
    const seen = stubFetch([
      { match: RETENTION_PATH, respond: () => jsonResponse({ changed_anything: false }) },
    ]);
    await runRetention();
    expect(seen[0]?.method).toBe('POST');
    expect(new URL(seen[0]?.url ?? '').pathname).toBe(`${RETENTION_PATH}/run`);
  });
});

describe('the audit read', () => {
  it('sends the window as ISO instants, with the filters it was given', async () => {
    const seen = stubFetch([
      { match: AUDIT_PATH, respond: () => jsonResponse({ items: [], next_before: null }) },
    ]);
    await fetchAudit({
      start: new Date('2026-10-05T00:00:00Z'),
      end: new Date('2026-10-06T00:00:00Z'),
      action: 'threshold.set',
      actor: 'ops@example.test',
      targetType: 'threshold',
      targetId: 'flow/high',
      before: 91,
      limit: 50,
    });
    const url = new URL(seen[0]?.url ?? '');
    expect(url.pathname).toBe(AUDIT_PATH);
    expect(url.searchParams.get('start')).toBe('2026-10-05T00:00:00.000Z');
    expect(url.searchParams.get('end')).toBe('2026-10-06T00:00:00.000Z');
    expect(url.searchParams.get('action')).toBe('threshold.set');
    expect(url.searchParams.get('actor')).toBe('ops@example.test');
    expect(url.searchParams.get('target_type')).toBe('threshold');
    expect(url.searchParams.get('target_id')).toBe('flow/high');
    expect(url.searchParams.get('before')).toBe('91');
    expect(url.searchParams.get('limit')).toBe('50');
  });

  it('omits every filter that was not set, rather than sending empty strings', async () => {
    const seen = stubFetch([
      { match: AUDIT_PATH, respond: () => jsonResponse({ items: [], next_before: null }) },
    ]);
    await fetchAudit({
      start: new Date('2026-10-05T00:00:00Z'),
      end: new Date('2026-10-06T00:00:00Z'),
    });
    const url = new URL(seen[0]?.url ?? '');
    for (const absent of ['action', 'actor', 'target_type', 'target_id', 'before', 'limit']) {
      expect(url.searchParams.has(absent)).toBe(false);
    }
  });
});
