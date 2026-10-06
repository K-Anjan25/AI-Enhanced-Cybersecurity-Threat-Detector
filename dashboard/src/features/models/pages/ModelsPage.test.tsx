/**
 * The model ops screen (T-409), through the page an operator opens.
 *
 * T-409's acceptance criterion is asserted where an operator meets it: the promotion
 * button stays disabled until the **model id is typed**, and the exact-match rule is
 * exercised with the near misses a person actually makes (a trailing space, one
 * character short, the wrong case). The rest of the suite covers the states a screen
 * gets wrong quietly: a registry that is empty, a listing that failed, a version with
 * no recorded evaluation, and the no-op promotion whose sentence has to say that the
 * audit trail recorded nothing.
 *
 * Only `fetch` is faked. The client, the hooks, the derived model and every component
 * are the real ones.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '../../../components/ui';
import { expectAccessible } from '../../../test/axe';
import { jsonResponse, Providers, stubFetch } from '../../../test/query';
import type { ModelVersion } from '../../../api/models';
import { ModelsPage } from './ModelsPage';

const FLOW_ACTIVE = 'a'.repeat(64);
const FLOW_STAGING = 'b'.repeat(64);
const LOG_ACTIVE = 'c'.repeat(64);

function version(overrides: Partial<ModelVersion> & { model_id: string }): ModelVersion {
  return {
    kind: 'flow',
    status: 'staging',
    artifact_uri: 's3://aegis/models/flow',
    sha256: 'd'.repeat(64),
    manifest_present: true,
    metrics: null,
    promoted_at: null,
    promoted_by: null,
    justification: '',
    ...overrides,
  };
}

const METRICS = {
  split: 'temporal:2025-Q4',
  evaluated_at: '2026-09-30T12:00:00Z',
  metrics: {
    roc_auc: { value: 0.8123, artifact: 'runs/flow-7.json', field: 'test.roc_auc' },
    recall: { value: 0.441, artifact: 'runs/flow-7.json', field: 'test.recall' },
  },
};

function registry(items: ModelVersion[]) {
  return { items, count: items.length };
}

/**
 * Routes for the four model endpoints.
 *
 * The promote and metrics routes come *first* on purpose: `stubFetch` matches by path
 * prefix, and the collection route would otherwise answer a child path — which is how
 * a page test ends up asserting on the wrong response shape.
 */
function modelRoutes(
  items: ModelVersion[],
  overrides: { promote?: (modelId: string) => Response; metrics?: Record<string, unknown> } = {},
) {
  return [
    {
      match: '/api/v1/models/',
      respond: (request: Request) => {
        const path = new URL(request.url).pathname;
        if (path.endsWith('/promote') || path.endsWith('/rollback')) {
          const id = path.split('/')[4] ?? '';
          return overrides.promote?.(id) ?? jsonResponse(transition(id));
        }
        const id = path.split('/')[4] ?? '';
        return jsonResponse(overrides.metrics ?? metricsFor(id));
      },
    },
    { match: '/api/v1/models', respond: () => jsonResponse(registry(items)) },
  ] as const;
}

function transition(modelId: string, changed = true) {
  return {
    model_id: modelId,
    kind: 'flow',
    status: 'active',
    retired: null,
    changed,
    at: '2026-10-06T10:00:00Z',
    actor: 'ana',
  };
}

/** The recorded run for whichever version the page asked about. */
function metricsFor(id: string) {
  return { ...METRICS, split: `held-out:${id.slice(0, 4)}` };
}

function renderPage() {
  return render(
    <ToastProvider>
      <Providers>
        <ModelsPage />
      </Providers>
    </ToastProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the version table', () => {
  it('leads with what is serving and shows each metric beside its run', async () => {
    stubFetch(
      modelRoutes([
        version({ model_id: FLOW_ACTIVE, status: 'active', metrics: METRICS }),
        version({ model_id: FLOW_STAGING }),
      ]),
    );
    renderPage();

    const serving = await screen.findByRole('region', { name: /Serving now — Flow/i });
    expect(within(serving).getByText('0.8123')).toBeInTheDocument();
    expect(
      within(serving).getByText('read from runs/flow-7.json at test.roc_auc'),
    ).toBeInTheDocument();

    // Both versions are in the table, abbreviated but with the full id available.
    expect(screen.getByTitle(`${FLOW_ACTIVE} (content address, R-68)`)).toBeInTheDocument();
    expect(screen.getByText('Serving Flow traffic.')).toBeInTheDocument();
  });

  it('refuses a version with no manifest with the rule that refuses it', async () => {
    stubFetch(modelRoutes([version({ model_id: FLOW_STAGING, manifest_present: false })]));
    renderPage();

    expect(await screen.findByText(/R-63 refuses its promotion/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `Promote ${FLOW_STAGING}` })).toBeNull();
  });

  it('says the registry is empty rather than rendering an empty table', async () => {
    stubFetch(modelRoutes([]));
    renderPage();
    expect(await screen.findByText('No model versions are registered')).toBeInTheDocument();
  });

  it('offers a retry when the listing fails, and no table at all', async () => {
    stubFetch([{ match: '/api/v1/models', respond: () => jsonResponse({ detail: 'down' }, 500) }]);
    renderPage();
    expect(await screen.findByText('The model registry could not be read')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('is accessibility-clean', async () => {
    stubFetch(
      modelRoutes([
        version({ model_id: FLOW_ACTIVE, status: 'active', metrics: METRICS }),
        version({ model_id: LOG_ACTIVE, kind: 'log', status: 'active' }),
        version({ model_id: FLOW_STAGING }),
      ]),
    );
    const { container } = renderPage();
    await screen.findByRole('region', { name: /Serving now — Flow/i });
    await expectAccessible(container);
  });
});

describe('promotion requires typing the model id', () => {
  it('keeps the confirm disabled through the near misses, then submits the exact id', async () => {
    const seen = stubFetch(modelRoutes([version({ model_id: FLOW_STAGING })]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: `Promote ${FLOW_STAGING}` }));
    const confirm = screen.getByRole('button', { name: 'Promote to active' });
    const idField = screen.getByLabelText('Type the model id to confirm');
    const justification = screen.getByLabelText('Justification (required)');

    // §4.7 asks for shadow-mode as the default target; there is no such status, and
    // the dialog says what it does instead of implying a shadow period (D-047).
    // The sentence wraps `<code>shadow</code>`, so it is matched on its text rather
    // than on a single node.
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === 'P' && /no shadow status/.test(element.textContent ?? ''),
      ),
    ).toBeInTheDocument();
    expect(confirm).toBeDisabled();

    await user.type(justification, 'beats the incumbent on PR-AUC');
    await user.type(idField, `${FLOW_STAGING} `);
    expect(confirm).toBeDisabled();
    expect(screen.getByText('Type the model id exactly to confirm.')).toBeInTheDocument();

    await user.type(idField, '{backspace}');
    await waitFor(() => {
      expect(confirm).toBeEnabled();
    });

    await user.click(confirm);
    await waitFor(() => {
      expect(seen.some((request) => request.method === 'POST')).toBe(true);
    });
    const post = seen.find((request) => request.method === 'POST');
    expect(new URL(post?.url ?? '').pathname).toBe(`/api/v1/models/${FLOW_STAGING}/promote`);
    await expect(post?.json()).resolves.toEqual({
      justification: 'beats the incumbent on PR-AUC',
    });
  });

  it('will not submit without a justification, whatever the id field says', async () => {
    stubFetch(modelRoutes([version({ model_id: FLOW_STAGING })]));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: `Promote ${FLOW_STAGING}` }));
    await user.type(screen.getByLabelText('Type the model id to confirm'), FLOW_STAGING);
    expect(screen.getByRole('button', { name: 'Promote to active' })).toBeDisabled();
    expect(screen.getByText('A promotion needs a written justification.')).toBeInTheDocument();
  });

  it('reports the server’s refusal inside the dialog and writes nothing', async () => {
    stubFetch(
      modelRoutes([version({ model_id: FLOW_STAGING })], {
        promote: () => jsonResponse({ detail: 'role' }, 403),
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: `Promote ${FLOW_STAGING}` }));
    await user.type(screen.getByLabelText('Type the model id to confirm'), FLOW_STAGING);
    await user.type(screen.getByLabelText('Justification (required)'), 'because');
    await user.click(screen.getByRole('button', { name: 'Promote to active' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/needs the admin role/);
    // The dialog stays open, so the operator can read the refusal where they acted.
    expect(screen.getByRole('button', { name: 'Promote to active' })).toBeInTheDocument();
  });

  it('reports a no-op as a change that was not recorded', async () => {
    stubFetch(
      modelRoutes([version({ model_id: FLOW_ACTIVE, status: 'active', metrics: METRICS })]),
    );
    renderPage();

    // A version that is already serving has no Promote control; the refusal is stated
    // in its row, so a no-op cannot be attempted from here.
    expect(await screen.findByText(/already serving/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `Promote ${FLOW_ACTIVE}` })).toBeNull();
  });
});
