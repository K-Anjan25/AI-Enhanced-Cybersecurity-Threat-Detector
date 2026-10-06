/**
 * The keys model (T-410, FR-44).
 *
 * The acceptance criterion is *the API key secret renders exactly once*, and the
 * mechanism that enforces it lives here: a secret is captured with the rendering that
 * received it (`expiresWith`), and `secretIsLive` is the one predicate that decides
 * whether it may be drawn. The test that matters is the negative one — the same capture
 * against a later rendering is not live — because that is the failure a screenshot
 * would never show: a modal closed and reopened, with the key still in a field.
 */
import { describe, expect, it } from 'vitest';

import type { ApiKey, ApiKeyIssued, ScopeInfo } from '../../api/admin';
import {
  SECRET_ONCE_NOTE,
  creationReadiness,
  issuedKey,
  keyRows,
  keySummary,
  scopeChoices,
  secretIsLive,
} from './keys';

const SECRET = 'aegis_sk_7_9f4c1d2e3a4b5c6d7e8f90a1b2c3d4e5'; // pragma: allowlist secret

function issued(over: Partial<ApiKeyIssued> = {}): ApiKeyIssued {
  return {
    id: 7,
    name: 'collector-01',
    prefix: 'aegis_sk_7_',
    owner: 'ops@example.test',
    scopes: ['ingest:write'],
    created_at: '2026-10-06T10:00:00Z',
    last_used_at: null,
    revoked_at: null,
    secret: SECRET,
    ...over,
  };
}

function listed(over: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 7,
    name: 'collector-01',
    prefix: 'aegis_sk_7_',
    owner: 'ops@example.test',
    scopes: ['ingest:write'],
    created_at: '2026-10-06T10:00:00Z',
    last_used_at: null,
    revoked_at: null,
    ...over,
  };
}

describe('the one-rendering lifetime', () => {
  it('is live for the rendering that captured it', () => {
    const capture = issuedKey(issued(), 3);
    expect(capture.secret).toBe(SECRET);
    expect(secretIsLive(capture, 3)).toBe(true);
  });

  it('is not live for a later rendering', () => {
    // Closing the dialog bumps the counter: this is exactly the sequence that would
    // otherwise leave a secret on screen in a reopened modal.
    const capture = issuedKey(issued(), 3);
    expect(secretIsLive(capture, 4)).toBe(false);
  });

  it('is not live when the dialog is closed, whatever the counter says', () => {
    const capture = issuedKey(issued(), 3);
    expect(secretIsLive(capture, null)).toBe(false);
  });

  it('is not live when there is no capture at all', () => {
    expect(secretIsLive(null, 3)).toBe(false);
    expect(secretIsLive(null, null)).toBe(false);
  });

  it('says the rule in one sentence, and that a lost key is re-issued', () => {
    expect(SECRET_ONCE_NOTE).toContain('only time this key is shown');
    expect(SECRET_ONCE_NOTE).toContain('re-issued');
  });
});

describe('keyRows', () => {
  it('carries the prefix and never a secret', () => {
    const rows = keyRows([listed()]);
    expect(rows[0]?.prefix).toBe('aegis_sk_7_');
    expect(JSON.stringify(rows)).not.toContain(SECRET);
    // The listing type has no secret field, so this is structural rather than a
    // formatting choice: there is nothing here that could render one.
    expect(Object.keys(rows[0] ?? {})).not.toContain('secret');
  });

  it('reads a key that has never been used as "never used", not as a date', () => {
    expect(keyRows([listed()])[0]?.lastUsedAt).toBe('never used');
  });

  it('marks a revoked key and keeps its instant', () => {
    const rows = keyRows([listed({ revoked_at: '2026-10-06T11:00:00Z' })]);
    expect(rows[0]?.revoked).toBe(true);
    expect(rows[0]?.revokedAt).not.toBe('');
  });

  it('is empty for an unread listing', () => {
    expect(keyRows(undefined)).toEqual([]);
  });
});

describe('keySummary', () => {
  it('counts live and revoked separately', () => {
    const summary = keySummary([listed(), listed({ id: 8, revoked_at: '2026-10-06T11:00:00Z' })]);
    expect(summary).toMatchObject({ total: 2, live: 1, revoked: 1 });
    expect(summary.note).toContain('Revoked keys keep their row');
  });

  it('explains an empty list rather than saying "0 keys"', () => {
    expect(keySummary([]).note).toContain('No keys have been issued');
    expect(keySummary(undefined).total).toBe(0);
  });
});

describe('scopeChoices', () => {
  it('keeps the server’s capabilities beside the scope name', () => {
    const scopes: ScopeInfo[] = [{ name: 'alerts:read', capabilities: ['read'] }];
    expect(scopeChoices(scopes)[0]?.capabilities).toEqual(['read']);
    expect(scopeChoices(scopes)[0]?.describes).toBe('read the alert list');
  });

  it('falls back to the capability list for an unknown scope', () => {
    expect(scopeChoices([{ name: 'x', capabilities: ['a', 'b'] }])[0]?.describes).toBe('a, b');
  });

  it('is empty when the scope read failed, so no key can be issued', () => {
    expect(scopeChoices(undefined)).toEqual([]);
  });
});

describe('creationReadiness', () => {
  it('needs a name', () => {
    expect(creationReadiness('   ', ['ingest:write'])).toEqual({
      ready: false,
      reason: 'A key needs a name to recognise it by.',
    });
  });

  it('needs at least one scope', () => {
    const readiness = creationReadiness('collector-01', []);
    expect(readiness.ready).toBe(false);
    expect(readiness.reason).toContain('at least one scope');
  });

  it('refuses a name longer than the API accepts', () => {
    expect(creationReadiness('n'.repeat(121), ['ingest:write']).ready).toBe(false);
  });

  it('is ready with a name and a scope, and trims the name in the reason it gives', () => {
    expect(creationReadiness(' collector-01 ', ['ingest:write'])).toEqual({
      ready: true,
      reason: null,
    });
  });
});
