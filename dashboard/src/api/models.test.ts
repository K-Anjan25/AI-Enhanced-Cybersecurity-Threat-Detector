/**
 * The model ops client's paths and bodies (T-409).
 *
 * The bodies are asserted rather than the calls: the API refuses a blank
 * justification (`min_length=1`), and a rollback carrying a version id would be a
 * request the server has no route for. What this client sends *is* the contract.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, stubFetch } from '../test/query';
import {
  MODELS_PATH,
  fetchModelMetrics,
  fetchModels,
  modelMetricsPath,
  promoteModel,
  promotePath,
  rollbackModel,
  rollbackPath,
} from './models';

const ID = 'a'.repeat(64);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('paths', () => {
  it('addresses a version’s metrics by its own id', () => {
    expect(modelMetricsPath(ID)).toBe(`${MODELS_PATH}/${ID}/metrics`);
  });

  it('keeps the model id inside one segment, even when it looks like a path', () => {
    const path = modelMetricsPath('latest/../..');
    // The round trip is the assertion: the id comes back whole, and the URL parser
    // did not collapse the `..` into a different route on the way.
    const url = new URL(path, 'https://aegis.example');
    expect(url.pathname.startsWith(`${MODELS_PATH}/`)).toBe(true);
    expect(url.pathname.endsWith('/metrics')).toBe(true);
    const idSegment = url.pathname.slice(MODELS_PATH.length + 1, -'/metrics'.length);
    expect(decodeURIComponent(idSegment)).toBe('latest/../..');
  });

  it('percent-encodes a space and a non-hex id', () => {
    expect(promotePath('a b')).toBe(`${MODELS_PATH}/a%20b/promote`);
    expect(rollbackPath('flow')).toBe(`${MODELS_PATH}/flow/rollback`);
    expect(modelMetricsPath(ID)).toBe(`${MODELS_PATH}/${ID}/metrics`);
  });
});

describe('reads', () => {
  it('sends the list filters only when they were set', async () => {
    const seen = stubFetch([
      { match: MODELS_PATH, respond: () => jsonResponse({ items: [], count: 0 }) },
    ]);
    await fetchModels({ kind: 'flow' });
    const url = new URL(seen[0]?.url ?? '');
    expect(url.pathname).toBe(MODELS_PATH);
    expect(url.searchParams.get('kind')).toBe('flow');
    expect(url.searchParams.has('status')).toBe(false);
  });

  it('adds no query string at all when nothing was asked for', async () => {
    const seen = stubFetch([
      { match: MODELS_PATH, respond: () => jsonResponse({ items: [], count: 0 }) },
    ]);
    await fetchModels();
    expect(new URL(seen[0]?.url ?? '').search).toBe('');
  });

  it('reads one version’s metrics from its own route', async () => {
    const body = {
      split: 'temporal:2025-Q4',
      evaluated_at: '2026-09-30T12:00:00Z',
      metrics: { f1: { value: 0.5, artifact: 'runs/1.json', field: 'test.f1' } },
      evaluation: null,
    };
    const seen = stubFetch([{ match: MODELS_PATH, respond: () => jsonResponse(body) }]);
    await expect(fetchModelMetrics(ID)).resolves.toEqual(body);
    expect(new URL(seen[0]?.url ?? '').pathname).toBe(`${MODELS_PATH}/${ID}/metrics`);
  });
});

describe('writes', () => {
  it('promotes with the justification in the body and nothing else', async () => {
    const seen = stubFetch([
      {
        match: MODELS_PATH,
        respond: () =>
          jsonResponse({
            model_id: ID,
            kind: 'flow',
            status: 'active',
            retired: null,
            changed: true,
            at: '2026-10-06T10:00:00Z',
            actor: 'ana',
          }),
      },
    ]);
    await promoteModel(ID, 'beats the incumbent on PR-AUC');
    const request = seen[0];
    expect(request?.method).toBe('POST');
    await expect(request?.json()).resolves.toEqual({
      justification: 'beats the incumbent on PR-AUC',
    });
  });

  it('rolls back by kind with a reason', async () => {
    const seen = stubFetch([
      {
        match: MODELS_PATH,
        respond: () =>
          jsonResponse({
            model_id: ID,
            kind: 'flow',
            status: 'active',
            retired: ID,
            changed: true,
            at: '2026-10-06T10:00:00Z',
            actor: 'ana',
          }),
      },
    ]);
    await rollbackModel('flow', 'the new one regressed recall');
    const request = seen[0];
    expect(new URL(request?.url ?? '').pathname).toBe(`${MODELS_PATH}/flow/rollback`);
    await expect(request?.json()).resolves.toEqual({ reason: 'the new one regressed recall' });
  });

  it('raises a refusal as an ApiError carrying the status and not the body (R-58)', async () => {
    stubFetch([{ match: MODELS_PATH, respond: () => jsonResponse({ detail: 'nope' }, 403) }]);
    const error = await promoteModel(ID, 'why').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(Error);
    expect((error as { status: number | null }).status).toBe(403);
    expect((error as Error).message).not.toContain('nope');
  });
});
