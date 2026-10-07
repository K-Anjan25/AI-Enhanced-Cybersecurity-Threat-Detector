/**
 * The connectors model (T-422, FR-21).
 *
 * Two claims live here rather than in a rendering test, because they are about shapes
 * rather than about pixels:
 *
 *   * **A secret cannot appear in the listing.** `connectorRows` builds from
 *     `WebhookTarget`, whose type has no secret field, so there is no code path that
 *     could put one in the table — the same guarantee `keyRows` carries for API keys.
 *     The capture is a separate type, and it carries the rendering that may draw it.
 *   * **A delivery record's endpoint is a join, not a field.** The record names its
 *     target by id (R-58), so the model states which target the row was matched on and
 *     says so plainly when there is no longer one to match: a deleted endpoint must not
 *     render as a blank cell.
 *
 * The readiness checks are deliberately *three of the server's rules*, not all of them:
 * the ones a browser can answer honestly. Which addresses R-55 accepts is the server's,
 * enforced on submit and again on every attempt; a second copy here would drift, and
 * the drift would look like a client bug.
 */
import { describe, expect, it } from 'vitest';

import type { DeliveryRecord, WebhookTarget } from '../../api/webhooks';
import {
  MAX_URL_LENGTH,
  SECRET_ONCE_NOTE,
  caveatText,
  connectorRows,
  connectorSummary,
  creationReadiness,
  deliveryRows,
  deliverySummary,
  floorLabel,
  hostOf,
  issuedConnector,
  outcomeLabel,
  outcomeTone,
} from './connectors';
import { secretIsLive } from './secrets';

const SECRET = 'hmac_9f4c1d2e3a4b5c6d7e8f90a1b2c3d4e5'; // pragma: allowlist secret

function target(over: Partial<WebhookTarget> = {}): WebhookTarget {
  return {
    id: 'wh_1',
    url: 'https://hooks.example.com/aegis',
    description: 'SOC shift handover',
    severity_floor: 'high',
    active: true,
    created_at: '2026-10-01T09:00:00Z',
    ...over,
  };
}

function delivery(over: Partial<DeliveryRecord> = {}): DeliveryRecord {
  return {
    delivery_id: 'd-1',
    target_id: 'wh_1',
    at: '2026-10-07T09:00:00Z',
    delivered: true,
    attempt_count: 1,
    waited_seconds: 0,
    outcome: 'delivered',
    status: 200,
    reason: 'ok',
    ...over,
  };
}

describe('the capture a fresh endpoint makes', () => {
  it('carries the secret and the rendering that may draw it', () => {
    const capture = issuedConnector({ ...target(), secret: SECRET }, 2);

    expect(capture.secret).toBe(SECRET);
    expect(capture.expiresWith).toBe(2);
    // The lifetime predicate is tested where it lives (`secrets.test.ts`); this asserts
    // the capture the panel makes is stamped like an API key's is.
    expect(secretIsLive(capture, 2)).toBe(true);
    expect(secretIsLive(capture, 3)).toBe(false);
    expect(secretIsLive(capture, null)).toBe(false);
  });

  it('says the rule in one sentence, and that the API cannot return it', () => {
    expect(SECRET_ONCE_NOTE).toContain('only time this signing secret is shown');
    expect(SECRET_ONCE_NOTE).toContain('no route that returns it');
    expect(SECRET_ONCE_NOTE).toContain('re-issued');
  });
});

describe('connectorRows', () => {
  it('draws an endpoint from the listing, which has no secret to leak', () => {
    const [row] = connectorRows([target()]);

    expect(row).toMatchObject({
      id: 'wh_1',
      url: 'https://hooks.example.com/aegis',
      host: 'hooks.example.com',
      description: 'SOC shift handover',
      severityLabel: 'High',
      active: true,
    });
    expect(Object.keys(row ?? {})).not.toContain('secret');
  });

  it('reads a missing description as an empty one, not as null on screen', () => {
    expect(connectorRows([target({ description: null })])[0]?.description).toBe('');
  });

  it('falls back to the URL when it cannot be parsed, rather than dropping the cell', () => {
    expect(hostOf('not a url')).toBe('not a url');
    expect(connectorRows([target({ url: 'not a url' })])[0]?.host).toBe('not a url');
  });
});

describe('connectorSummary', () => {
  it('counts the endpoints and the floors they receive at', () => {
    const summary = connectorSummary([
      target(),
      target({ id: 'wh_2', severity_floor: 'critical' }),
      target({ id: 'wh_3', severity_floor: 'critical' }),
    ]);

    expect(summary.total).toBe(3);
    expect(summary.floors).toBe('1 at high, 2 at critical');
    expect(summary.note).toContain('3 registered');
  });

  it('reads an empty list as a fact about the deployment', () => {
    const summary = connectorSummary([]);

    expect(summary.total).toBe(0);
    expect(summary.note).toContain('nothing leaves this deployment');
  });
});

describe('creationReadiness', () => {
  it('refuses an empty URL, a non-https one, and one past the API’s limit', () => {
    expect(creationReadiness('  ', []).ready).toBe(false);
    expect(creationReadiness('', []).reason).toContain('needs a URL');
    expect(creationReadiness('http://hooks.example.com/x', []).reason).toContain('https');
    expect(creationReadiness(`https://x/${'a'.repeat(MAX_URL_LENGTH)}`, []).reason).toContain(
      String(MAX_URL_LENGTH),
    );
  });

  it('refuses a URL already registered, because that would deliver twice', () => {
    const known = ['https://hooks.example.com/aegis'];

    expect(creationReadiness('https://hooks.example.com/aegis', known).reason).toContain(
      'already registered',
    );
    expect(creationReadiness(' https://hooks.example.com/aegis ', known).ready).toBe(false);
    expect(creationReadiness('https://hooks.example.com/other', known).ready).toBe(true);
  });

  it('accepts a URL it has no honest reason to refuse, and says nothing', () => {
    // A private address is the server's refusal (R-55), not this module's: it re-checks
    // the allowlist and the resolution on every attempt.
    const readiness = creationReadiness('https://169.254.169.254/latest', []);

    expect(readiness).toEqual({ ready: true, reason: null });
  });
});

describe('deliveryRows', () => {
  it('joins a record to its endpoint and states the join', () => {
    const [row] = deliveryRows([delivery()], [target()], Date.parse('2026-10-07T09:03:00Z'));

    expect(row).toMatchObject({
      deliveryId: 'd-1',
      endpoint: 'hooks.example.com',
      endpointDetail: 'target wh_1',
      outcomeLabel: 'Delivered',
      tone: 'neutral',
      status: '200',
      reason: 'ok',
      attempts: '1 attempt',
      age: '3 m ago',
    });
  });

  it('says an endpoint is gone rather than rendering a blank one', () => {
    const [row] = deliveryRows([delivery({ target_id: 'wh_9' })], [target()], 0);

    expect(row?.endpoint).toBe('wh_9');
    expect(row?.endpointDetail).toBe('no longer configured');
  });

  it('reads a retry as its two requests and the time spent waiting', () => {
    const [row] = deliveryRows(
      [
        delivery({
          delivered: false,
          attempt_count: 2,
          waited_seconds: 1.5,
          outcome: 'retry',
          status: 500,
          reason: 'retryable_status',
        }),
      ],
      [target()],
    );

    expect(row?.attempts).toBe('2 attempts');
    expect(row?.waited).toBe('1.5s backoff');
    expect(row?.outcomeLabel).toBe('Retry');
    expect(row?.tone).toBe('high');
  });

  it('prints a dash rather than a null status, and names a transport error', () => {
    const [row] = deliveryRows(
      [delivery({ delivered: false, outcome: 'transport_error', status: null, reason: 'timeout' })],
      [target()],
    );

    expect(row?.status).toBe('—');
    expect(row?.outcomeLabel).toBe('Transport error');
    expect(row?.reason).toBe('timeout');
  });

  it('reads an empty history as no rows, whatever the endpoints are', () => {
    expect(deliveryRows([], [target()])).toEqual([]);
    expect(deliveryRows(undefined, undefined)).toEqual([]);
  });
});

describe('outcomeTone', () => {
  it('marks what needs looking at and leaves a delivery on the neutral chip', () => {
    // Urgency, not severity: the colour says what to read first, the word beside it says
    // what happened, and nothing is encoded in colour alone (NFR-09).
    expect(outcomeTone('delivered')).toBe('neutral');
    expect(outcomeTone('blocked')).toBe('critical');
    for (const outcome of ['retry', 'rejected', 'transport_error']) {
      expect(outcomeTone(outcome)).toBe('high');
    }
  });
});

describe('deliverySummary', () => {
  const base = { held: 2, recorded: 2, dispatch_configured: true, caveats: [] };

  it('counts what was delivered and how much of the history is on screen', () => {
    const summary = deliverySummary({
      ...base,
      items: [delivery(), delivery({ delivery_id: 'd-2', delivered: false, outcome: 'retry' })],
    });

    expect(summary.note).toContain('1 of 2 delivered');
    expect(summary.note).toContain('All 2 attempted are shown');
  });

  it('says when the window is a window rather than the whole history', () => {
    const summary = deliverySummary({
      ...base,
      recorded: 112,
      items: [delivery()],
    });

    expect(summary.note).toContain('Showing the newest 1 of 112 attempted');
  });

  it('separates "nothing has happened" from "nothing can happen"', () => {
    const quiet = deliverySummary({ ...base, items: [], recorded: 0 });
    const impossible = deliverySummary({
      ...base,
      items: [],
      recorded: 0,
      dispatch_configured: false,
    });

    expect(quiet.dispatchConfigured).toBe(true);
    expect(quiet.note).toContain('Nothing has been delivered yet');
    expect(impossible.dispatchConfigured).toBe(false);
    expect(impossible.note).toContain('no outbound transport');
  });

  it('says so when every attempt has aged out of the window', () => {
    const aged = deliverySummary({ ...base, items: [], recorded: 40 });

    expect(aged.note).toContain('these have aged out');
  });

  it('keeps the server’s caveats exactly as the server wrote them', () => {
    const list = {
      ...base,
      items: [],
      caveats: ['Delivery records live in this process’s memory.'],
    };

    expect(caveatText(list)).toEqual(['Delivery records live in this process’s memory.']);
    expect(caveatText(undefined)).toEqual([]);
  });
});

describe('floorLabel and outcomeLabel', () => {
  it('title-cases a floor the API returned, so a badge does not read `high`', () => {
    expect(floorLabel('high')).toBe('High');
    expect(floorLabel('critical')).toBe('Critical');
  });

  it('spaces an outcome code for reading, keeping it recognisable', () => {
    expect(outcomeLabel('transport_error')).toBe('Transport error');
    expect(outcomeLabel('delivered')).toBe('Delivered');
  });
});
